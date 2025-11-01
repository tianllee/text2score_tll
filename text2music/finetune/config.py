import os

# Configuration for the data
DATA_TRAIN_INDEX_PATH = "text2music/data/train_with_genres.jsonl" 
DATA_EVAL_INDEX_PATH  = "text2music/data/validation_with_genres.jsonl"
DATA_ROOT = "/data/scratch/eey549/ABC_Dataset/ABC_Dataset/"               # Root directory for the data

# Configuration for the small model
PATCH_STREAM = True
PATCH_SIZE = 16                                                # Patch Size
PATCH_LENGTH = 2048                                             # Patch Length
CHAR_NUM_LAYERS = 3                                             # Number of layers in the decoder
PATCH_NUM_LAYERS = 16                                           # Number of layers in the encoder
HIDDEN_SIZE = 768                                               # Hidden Size

# Configuration for the training
BATCH_SIZE = 8         
LEARNING_RATE = 1e-5   
NUM_EPOCHS = 10 #64                                                 # Number of epochs to train for (if early stopping doesn't intervene)
ACCUMULATION_STEPS = 1                                          # Accumulation steps to simulate large batch size
PATCH_SAMPLING_BATCH_SIZE = 0                                   # Batch size for patch during training, 0 for full conaudio
LOAD_FROM_CHECKPOINT = False                                    # Whether to load weights from a checkpoint
WANDB_LOGGING = False                                           # Whether to log to wandb
WANDB_KEY = '6b550a00b0715f51d4ec8860fe338c9823a77cf7'

PRETRAINED_PATH = "/data/home/acw769/text2score/weights_notagen_pretrain_p_size_16_p_length_2048_p_layers_16_c_layers_3_h_size_768_lr_0.0001_batch_8.pth"                # Path of pretrained weights
EXP_TAG = 'finetune'                                            # Experiment tag for name differentiation
NAME =  EXP_TAG + \
        "_p_size_" + str(PATCH_SIZE) + \
        "_p_length_" + str(PATCH_LENGTH) + \
        "_p_layers_" + str(PATCH_NUM_LAYERS) + \
        "_c_layers_" + str(CHAR_NUM_LAYERS) + \
        "_h_size_" + str(HIDDEN_SIZE) + \
        "_lr_" + str(LEARNING_RATE) + \
        "_batch_" + str(BATCH_SIZE)

WEIGHTS_PATH = "weights_notagen_" + NAME + ".pth"                  # Path to save weights
LOGS_PATH    = "logs_notagen_"    + NAME + ".txt"                     # Path to save logs
WANDB_NAME = NAME
