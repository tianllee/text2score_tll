import os
import gc
import time
import weakref
import json
import wandb
import torch
import random
import pickle
import numpy as np
from utils import *
from config import *
from text2music.data.utils.xml2plan import get_partial_plan_text, get_full_plan_text
from text2music.data.utils.abci_augment import read_abci_with_pitch_shift
from tqdm import tqdm
from torch.amp import autocast, GradScaler
from torch.utils.data import Dataset, DataLoader
from transformers import GPT2Config, get_scheduler, get_constant_schedule_with_warmup
import torch.distributed as dist
from torch.nn.parallel import DistributedDataParallel as DDP
from torch.utils.data.distributed import DistributedSampler
from torch.utils.data import IterableDataset

# Set up distributed training
world_size = int(os.environ['WORLD_SIZE']) if 'WORLD_SIZE' in os.environ else 1
global_rank = int(os.environ['RANK']) if 'RANK' in os.environ else 0
local_rank = int(os.environ['LOCAL_RANK']) if 'LOCAL_RANK' in os.environ else 0

if world_size > 1:
    torch.cuda.set_device(local_rank)
    device = torch.device("cuda", local_rank)
    dist.init_process_group(backend='nccl') if world_size > 1 else None
else:
    device = torch.device("cuda") if torch.cuda.is_available() else torch.device("cpu")

# Set random seed
seed = 0 + global_rank
random.seed(seed)
np.random.seed(seed)
torch.manual_seed(seed)
torch.cuda.manual_seed_all(seed)
torch.backends.cudnn.deterministic = True
torch.backends.cudnn.benchmark = False

batch_size = BATCH_SIZE

patchilizer = Patchilizer()

patch_config = GPT2Config(num_hidden_layers=PATCH_NUM_LAYERS,
                          max_length=PATCH_LENGTH,
                          max_position_embeddings=PATCH_LENGTH,
                          n_embd=HIDDEN_SIZE,
                          num_attention_heads=HIDDEN_SIZE // 64,
                          vocab_size=1)
char_config = GPT2Config(num_hidden_layers=CHAR_NUM_LAYERS,
                         max_length=PATCH_SIZE + 1,
                         max_position_embeddings=PATCH_SIZE + 1,
                         hidden_size=HIDDEN_SIZE,
                         num_attention_heads=HIDDEN_SIZE // 64,
                         vocab_size=128)


def clear_unused_tensors():
    gc.disable()  # Temporarily disable garbage collection
    try:
        # Get the set of tensor ids used by the model
        if hasattr(model, "module"):
            model_tensors = {id(p) for p in model.module.parameters()}
        else:
            model_tensors = {id(p) for p in model.parameters()}

        # Get the set of tensor ids used by the optimizer
        optimizer_tensors = {
            id(state)
            for state_dict in optimizer.state.values()
            for state in state_dict.values()
            if isinstance(state, torch.Tensor)  # Ensure only tensors are considered
        }

        # List of all CUDA tensors currently in memory
        tensors = [obj for obj in gc.get_objects() if isinstance(obj, torch.Tensor) and obj.is_cuda]

        # Create weak references to avoid interfering with garbage collection
        tensor_refs = [weakref.ref(tensor) for tensor in tensors]

        for tensor_ref in tensor_refs:
            tensor = tensor_ref()  # Dereference the weak reference
            if tensor is not None and id(tensor) not in model_tensors and id(tensor) not in optimizer_tensors:
                # Mark the tensor for deletion
                tensor.detach_()  # Detach from computation graph
                del tensor  # Delete the tensor reference
    except:
        pass

    finally:
        gc.enable()  # Re-enable garbage collection
        gc.collect()  # Force a garbage collection
        torch.cuda.empty_cache()  # Clear the CUDA cache


def collate_batch(input_batches):

    input_patches, input_plan, input_masks = zip(*input_batches)
    input_patches = torch.nn.utils.rnn.pad_sequence(input_patches, batch_first=True, padding_value=0)
    input_plan = torch.nn.utils.rnn.pad_sequence(input_plan, batch_first=True, padding_value=0)
    input_masks = torch.nn.utils.rnn.pad_sequence(input_masks, batch_first=True, padding_value=0)

    return input_patches, input_plan, input_masks

def split_into_minibatches(input_patches, input_plan, input_masks, minibatch_size):
    minibatches = []
    for start_idx in range(0, len(input_patches), minibatch_size):
        end_idx = start_idx + minibatch_size
        minibatch_patches = input_patches[start_idx:end_idx]
        minibatch_plan = input_plan[start_idx:end_idx]  # Slice the plan
        minibatch_masks = input_masks[start_idx:end_idx]
        # Return plan in the tuple
        minibatches.append((minibatch_patches, minibatch_plan, minibatch_masks))
    return minibatches


class ResamplingStreamingDataset(IterableDataset):
    def __init__(self, file_path, data_root, pitch_shift_range=(0, 0), buffer_size=1000):
        self.file_path = file_path
        self.data_root = data_root
        self.pitch_shift_range = pitch_shift_range
        self.buffer_size = buffer_size
        self.epoch = 0  # Track epoch for deterministic shuffling
        
        # --- PHASE 1: Light Indexing ---
        # We scan the file to get byte offsets and count unique files.
        # We do NOT store the text/json in memory.
        self.all_offsets = []
        self.unique_count = 0
        
        print(f"Indexing {file_path}...")
        with open(file_path, 'r', encoding='utf-8') as f:
            while True:
                offset = f.tell()
                line = f.readline()
                if not line:
                    break
                
                # Store the offset of this line
                self.all_offsets.append(offset)
                
                # Check for uniqueness (Fast check without full JSON parse if possible)
                # We assume 'augmented' is in the path string as per your original logic
                if 'augmented' not in line: 
                    self.unique_count += 1
        
        print(f"Indexing complete.")
        print(f"Total Files: {len(self.all_offsets)}")
        print(f"Unique Files: {self.unique_count}")
        print(f"Epoch Length will be: {self.unique_count}")

    def set_epoch(self, epoch):
        """Called by the training loop to update the random seed."""
        self.epoch = epoch

    def __len__(self):
        # We emulate the length of the unique set
        return self.unique_count

    def _parse_line(self, line):
        """Parses a single line of json and processes it."""
        try:
            record = json.loads(line)
            filepath = record['path']
            filepath = os.path.join(self.data_root, filepath)
            genre = record.get('genre', None)

            # Pitch Shift
            pitch_shift = 0
            if self.pitch_shift_range != (0, 0):
                pitch_shift = random.randint(*self.pitch_shift_range)
            
            # Read ABC
            abc_text = read_abci_with_pitch_shift(filepath, pitch_shift=pitch_shift)
            
            # Read Plan
            pkl_path = filepath.replace('.abci', '.pkl')
            if os.path.exists(pkl_path):
                # Note: Assuming get_full_plan_text reads the pickle itself or you pass the path
                plan = get_full_plan_text(pkl_path, pitch_shift=pitch_shift, genre=genre)
                file_plan = patchilizer.encode_plan(plan)
            else:
                file_plan = patchilizer.encode_plan("")

            file_bytes = patchilizer.encode_train(abc_text)
            file_masks = [1] * len(file_bytes)

            return (torch.tensor(file_bytes, dtype=torch.long), 
                    file_plan, 
                    torch.tensor(file_masks, dtype=torch.long))
        except Exception as e:
            # print(f"Error processing line: {e}")
            return None

    def __iter__(self):
        worker_info = torch.utils.data.get_worker_info()
        num_workers = 1 if worker_info is None else worker_info.num_workers
        worker_id = 0 if worker_info is None else worker_info.id
        
        # Global worker ID for DDP + Multi-worker
        # Note: We don't strictly need global ID for sharding the *sampled list* if we seed correctly,
        # but it helps to keep logic clean.
        
        # --- SAMPLING LOGIC ---
        # 1. Deterministic Randomness based on Epoch
        # This ensures all workers generate the exact same "random" list of offsets to start with.
        rng = random.Random(self.epoch + 999) 
        
        # 2. Re-sample the dataset (Your original logic: choices with replacement?)
        # Your original code used random.choices (with replacement). 
        # If you wanted without replacement, use random.sample.
        # We will use choices to match your original code.
        epoch_offsets = rng.choices(self.all_offsets, k=self.unique_count)
        
        # 3. Shard the sampled list for this worker
        # Each worker only processes its slice of the sampled list
        my_offsets = epoch_offsets[worker_id::num_workers]
        
        # 4. Stream data
        with open(self.file_path, 'r', encoding='utf-8') as f:
            for offset in my_offsets:
                f.seek(offset)
                line = f.readline()
                sample = self._parse_line(line)
                
                if sample is not None:
                    yield sample


def process_one_batch(patches, plan, masks):
    # Direct forward pass
    loss = model(plan, patches, masks).loss

    # Reduce the loss on GPU 0 if using DDP
    if world_size > 1:
        loss = loss.unsqueeze(0)
        dist.reduce(loss, dst=0)
        loss = loss / world_size
        dist.broadcast(loss, src=0)

    return loss


def train_epoch(epoch, dataloader, steps_per_epoch):
    # Pass 'total' to tqdm so the progress bar works
    tqdm_train_set = tqdm(dataloader, total=steps_per_epoch, disable=(global_rank!=0))
    
    total_train_loss = 0
    iter_idx = 1
    model.train()
    
    optimizer.zero_grad(set_to_none=True) 

    for batch_idx, batch in enumerate(tqdm_train_set):
        input_patches = batch[0].to(device, non_blocking=True)
        plan = batch[1].to(device, non_blocking=True)
        input_masks = batch[2].to(device, non_blocking=True)
        
        with autocast("cuda", dtype=torch.bfloat16):
            loss = process_one_batch(input_patches, plan, input_masks)
            loss = loss / ACCUMULATION_STEPS

        loss.backward()
        
        current_loss_float = loss.item() * ACCUMULATION_STEPS
        total_train_loss += current_loss_float

        if (batch_idx + 1) % ACCUMULATION_STEPS == 0:
            optimizer.step()
            lr_scheduler.step()
            optimizer.zero_grad(set_to_none=True)

        tqdm_train_set.set_postfix({"train_loss": total_train_loss / iter_idx})
        
        if global_rank == 0 and WANDB_LOGGING and (batch_idx + 1) % ACCUMULATION_STEPS == 0:
            # FIXED: Use calculated steps_per_epoch
            train_steps = (epoch - 1) * steps_per_epoch + batch_idx
            wandb.log({"train_loss": total_train_loss / iter_idx}, step=train_steps)

        iter_idx += 1
        
        del input_patches, plan, input_masks, loss
        if iter_idx % 100 == 0:
            import gc
            gc.collect() 
            torch.cuda.empty_cache()

    return total_train_loss / (iter_idx - 1)


def eval_epoch():
    tqdm_eval_set = tqdm(eval_set)
    total_eval_loss = 0
    iter_idx = 1
    model.eval()

    for batch in tqdm_eval_set:
        input_patches, plan, input_masks = batch[0].to(device), batch[1].to(device), batch[2].to(device)
        
        with torch.no_grad():
            with autocast("cuda", dtype=torch.bfloat16):
                # No splitting needed, just run the batch
                loss = process_one_batch(input_patches, plan, input_masks)
                
        total_eval_loss += loss.item()
        tqdm_eval_set.set_postfix({str(global_rank) + '_eval_loss': total_eval_loss / iter_idx})
        iter_idx += 1
        
    return total_eval_loss / (iter_idx - 1)


# train and eval
if __name__ == "__main__":

    # Initialize wandb
    if WANDB_LOGGING and global_rank == 0:
        wandb.login(key=WANDB_KEY)
        wandb.init(project="notagen", name=WANDB_NAME)

    # --- CHANGED: Use Streaming Dataset ---
    print("Initializing Streaming Datasets...")
    
    # Configure buffer size based on available RAM
    train_set = ResamplingStreamingDataset(
        file_path=DATA_TRAIN_INDEX_PATH, 
        data_root=DATA_ROOT, 
        pitch_shift_range=(0, 0)
    )
    
    eval_set = ResamplingStreamingDataset(
        file_path=DATA_EVAL_INDEX_PATH, 
        data_root=DATA_ROOT, 
        pitch_shift_range=(0, 0)
    )
    
    train_loader = DataLoader(
        train_set, 
        batch_size=batch_size, 
        collate_fn=collate_batch, 
        num_workers=4, 
        pin_memory=True
    )
    
    eval_loader = DataLoader(
        eval_set, 
        batch_size=batch_size, 
        collate_fn=collate_batch, 
        num_workers=2, 
        pin_memory=True
    )

    # --- Calculate Steps Per Epoch ---
    # We need this because the DataLoader is iterable and has no len() for tqdm
    total_samples = len(train_set)
    # Total batches = Total Samples // (Batch Size per GPU * Number of GPUs)
    steps_per_epoch = total_samples // (batch_size * world_size)
    
    if global_rank == 0:
        print(f"Total Training Samples: {total_samples}")
        print(f"Calculated Steps per Epoch: {steps_per_epoch}")

    # --- Model Initialization ---
    model = CustomLMHeadModel(encoder_config=patch_config, decoder_config=char_config)
    print("Parameter Number: "+str(sum(p.numel() for p in model.parameters() if p.requires_grad)))
    
    optimizer = torch.optim.AdamW(model.parameters(), lr=LEARNING_RATE)
    lr_scheduler = get_constant_schedule_with_warmup(optimizer=optimizer, num_warmup_steps=1000)
    scaler = GradScaler() # Kept for compatibility

    pre_epoch = 0
    best_epoch = 0
    min_eval_loss = 100

    # --- Checkpoint Loading ---
    if not LOAD_FROM_CHECKPOINT:
        # Load Pretrained Weights Logic
        if os.path.exists(WEIGHTS_PATH):
            checkpoint = torch.load(WEIGHTS_PATH, map_location='cpu')
            print(f"Loading Pretrained Checkpoint (Epoch {checkpoint.get('epoch', '?')})")

            state_dict = checkpoint['model']
            if any(key.startswith('module.') for key in state_dict.keys()):
                from collections import OrderedDict
                new_state_dict = OrderedDict()
                for k, v in state_dict.items():
                    name = k[7:] # remove `module.`
                    new_state_dict[name] = v
                model.load_state_dict(new_state_dict)
            else:
                model.load_state_dict(state_dict)
            
            # Reset for finetuning
            pre_epoch = 0 
            best_epoch = 0
            min_eval_loss = 100 
            
            del checkpoint, state_dict
            gc.collect()
            torch.cuda.empty_cache()
        else:
            raise Exception('Pre-trained Checkpoint not found.')
            
    else: 
        # Resume Finetuning Logic
        if os.path.exists(WEIGHTS_PATH):
            checkpoint = torch.load(WEIGHTS_PATH, map_location='cpu')
            
            state_dict = checkpoint['model']
            if any(key.startswith('module.') for key in state_dict.keys()):
                from collections import OrderedDict
                new_state_dict = OrderedDict()
                for k, v in state_dict.items():
                    name = k[7:] # remove `module.`
                    new_state_dict[name] = v
                model.load_state_dict(new_state_dict)
            else:
                model.load_state_dict(state_dict)
                
            optimizer.load_state_dict(checkpoint['optimizer'])
            lr_scheduler.load_state_dict(checkpoint['lr_sched'])
            pre_epoch = checkpoint['epoch']
            best_epoch = checkpoint['best_epoch']
            # min_eval_loss = checkpoint.get('min_eval_loss', 100)
            
            print(f"Successfully Loaded Resumption Checkpoint from Epoch {pre_epoch}")
            
            del checkpoint, state_dict
            gc.collect()
            torch.cuda.empty_cache()
        else:
            print("Checkpoint not found, starting fresh (or check path).")

    # --- Move to Device ---
    model = model.to(device)

    # Move optimizer state
    for state in optimizer.state.values():
        for k, v in state.items():
            if isinstance(v, torch.Tensor):
                state[k] = v.to(device)

    # --- DDP Wrap ---
    if world_size > 1:
        model = DDP(model, device_ids=[local_rank], output_device=local_rank, find_unused_parameters=True)

    # --- Training Loop ---
    for epoch in range(1 + pre_epoch, NUM_EPOCHS + 1):
        # Note: No train_sampler.set_epoch needed for IterableDataset
        
        print('-' * 21 + "Epoch " + str(epoch) + '-' * 21)

        # Update the epoch in the dataset so it re-samples differently!
        train_set.set_epoch(epoch)
        eval_set.set_epoch(epoch)
        
        # Pass steps_per_epoch explicitly
        train_loss = train_epoch(epoch, train_loader, steps_per_epoch)
        eval_loss = eval_epoch(eval_loader)
        
        if global_rank == 0:
            with open(LOGS_PATH, 'a') as f:
                f.write("Epoch " + str(epoch) + "\ntrain_loss: " + str(train_loss) + "\neval_loss: " + str(eval_loss) +
                        "\ntime: " + time.asctime(time.localtime(time.time())) + "\n\n")
            
            if eval_loss < min_eval_loss:
                best_epoch = epoch
                min_eval_loss = eval_loss
                checkpoint = {
                    'model': model.module.state_dict() if hasattr(model, "module") else model.state_dict(),
                    'optimizer': optimizer.state_dict(),
                    'lr_sched': lr_scheduler.state_dict(),
                    'epoch': epoch,
                    'best_epoch': best_epoch,
                    'min_eval_loss': min_eval_loss
                }
                torch.save(checkpoint, WEIGHTS_PATH)

        if world_size > 1:
            dist.barrier()

    if global_rank == 0:
        print("Best Eval Epoch : " + str(best_epoch))
        print("Min Eval Loss : " + str(min_eval_loss))