
import os
import time
import torch
from utils import *
from config import *
from transformers import GPT2Config, LlamaConfig
from text2music.data.utils.abc_helper.abctoolkit_v006_mod.transpose import Note_list
from text2music.data.utils.abc_helper.abctoolkit_v006_mod.duration import calculate_bartext_duration
from text2music.data.utils.abc_helper.abctoolkit_v006_mod.utils import Barline_regexPattern
import shutil

Note_list = Note_list + ['z', 'x']

if torch.cuda.is_available():
    device = torch.device("cuda")
else:
    device = torch.device("cpu")

if os.path.exists(ORIGINAL_OUTPUT_FOLDER):
    shutil.rmtree(ORIGINAL_OUTPUT_FOLDER)
if os.path.exists(INTERLEAVED_OUTPUT_FOLDER):
    shutil.rmtree(INTERLEAVED_OUTPUT_FOLDER)
if os.path.exists(XML_OUTPUT_FOLDER):
    shutil.rmtree(XML_OUTPUT_FOLDER)

os.makedirs(ORIGINAL_OUTPUT_FOLDER, exist_ok=True)
os.makedirs(INTERLEAVED_OUTPUT_FOLDER, exist_ok=True)

patchilizer = Patchilizer()

patch_config = GPT2Config(num_hidden_layers=PATCH_NUM_LAYERS,
                          max_length=PATCH_LENGTH,
                          max_position_embeddings=PATCH_LENGTH,
                          n_embd=HIDDEN_SIZE,
                          num_attention_heads=HIDDEN_SIZE // 64,
                          vocab_size=1)
byte_config = GPT2Config(num_hidden_layers=CHAR_NUM_LAYERS,
                         max_length=PATCH_SIZE + 1,
                         max_position_embeddings=PATCH_SIZE + 1,
                         hidden_size=HIDDEN_SIZE,
                         num_attention_heads=HIDDEN_SIZE // 64,
                         vocab_size=128)

# model = NotaGenLMHeadModel(encoder_config=patch_config, decoder_config=byte_config)
model = CustomLMHeadModel(encoder_config=patch_config, decoder_config=byte_config)

print("Parameter Number: " + str(sum(p.numel() for p in model.parameters() if p.requires_grad)))

checkpoint = torch.load(INFERENCE_WEIGHTS_PATH, map_location=torch.device(device))
model.load_state_dict(checkpoint['model'])
model = model.to(device)
model.eval()


def rest_unreduce(abc_lines):

    tunebody_index = None
    for i in range(len(abc_lines)):
        if '[V:' in abc_lines[i]:
            tunebody_index = i
            break

    metadata_lines = abc_lines[: tunebody_index]
    tunebody_lines = abc_lines[tunebody_index:]

    part_symbol_list = []
    voice_group_list = []
    for line in metadata_lines:
        if line.startswith('%%score'):
            for round_bracket_match in re.findall(r'\((.*?)\)', line):
                voice_group_list.append(round_bracket_match.split())
            existed_voices = [item for sublist in voice_group_list for item in sublist]
        if line.startswith('V:'):
            symbol = line.split()[0]
            part_symbol_list.append(symbol)
            if symbol[2:] not in existed_voices:
                voice_group_list.append([symbol[2:]])
    z_symbol_list = []  # voices that use z as rest
    x_symbol_list = []  # voices that use x as rest
    for voice_group in voice_group_list:
        z_symbol_list.append('V:' + voice_group[0])
        for j in range(1, len(voice_group)):
            x_symbol_list.append('V:' + voice_group[j])

    part_symbol_list.sort(key=lambda x: int(x[2:]))

    unreduced_tunebody_lines = []

    for i, line in enumerate(tunebody_lines):
        unreduced_line = ''

        line = re.sub(r'^\[r:[^\]]*\]', '', line)

        pattern = r'\[V:(\d+)\](.*?)(?=\[V:|$)'
        matches = re.findall(pattern, line)

        line_bar_dict = {}
        for match in matches:
            key = f'V:{match[0]}'
            value = match[1]
            line_bar_dict[key] = value

        # calculate duration and collect barline
        dur_dict = {}  
        for symbol, bartext in line_bar_dict.items():
            right_barline = ''.join(re.split(Barline_regexPattern, bartext)[-2:])
            bartext = bartext[:-len(right_barline)]
            try:
                bar_dur = calculate_bartext_duration(bartext)
            except:
                bar_dur = None
            if bar_dur is not None:
                if bar_dur not in dur_dict.keys():
                    dur_dict[bar_dur] = 1
                else:
                    dur_dict[bar_dur] += 1

        try:
            ref_dur = max(dur_dict, key=dur_dict.get)
        except:
            pass    # use last ref_dur

        if i == 0:
            prefix_left_barline = line.split('[V:')[0]
        else:
            prefix_left_barline = ''

        for symbol in part_symbol_list:
            if symbol in line_bar_dict.keys():
                symbol_bartext = line_bar_dict[symbol]
            else:
                if symbol in z_symbol_list:
                    symbol_bartext = prefix_left_barline + 'z' + str(ref_dur) + right_barline
                elif symbol in x_symbol_list:
                    symbol_bartext = prefix_left_barline + 'x' + str(ref_dur) + right_barline
            unreduced_line += '[' + symbol + ']' + symbol_bartext

        unreduced_tunebody_lines.append(unreduced_line + '\n')

    unreduced_lines = metadata_lines + unreduced_tunebody_lines

    return unreduced_lines


def inference_patch(plan="", prompt_lines=[], pieces=NUM_SAMPLES):

    file_no = 1

    bos_patch = [patchilizer.bos_token_id] * (PATCH_SIZE - 1) + [patchilizer.eos_token_id]

    while file_no <= pieces:

        start_time = time.time()
        start_time_format = time.strftime("%Y%m%d-%H%M%S")

        prompt_patches = patchilizer.patchilize_metadata(prompt_lines)
        byte_list = list(''.join(prompt_lines))
        print(''.join(byte_list), end='')

        prompt_patches = [[ord(c) for c in patch] + [patchilizer.special_token_id] * (PATCH_SIZE - len(patch)) for patch
                          in prompt_patches]
        prompt_patches.insert(0, bos_patch)

        input_patches = torch.tensor(prompt_patches, device=device).reshape(1, -1)

        input_plan = patchilizer.encode_plan(plan).to(device)

        failure_flag = False
        end_flag = False
        cut_index = None

        tunebody_flag = False
        while True:
            predicted_patch = model.generate(input_plan.unsqueeze(0),
                                             input_patches.unsqueeze(0),
                                             top_k=TOP_K,
                                             top_p=TOP_P,
                                             temperature=TEMPERATURE)
            if not tunebody_flag and patchilizer.decode([predicted_patch]).startswith('[r:'):  # start with [r:0/
                tunebody_flag = True
                r0_patch = torch.tensor([ord(c) for c in '[r:0/']).unsqueeze(0).to(device)
                temp_input_patches = torch.concat([input_patches, r0_patch], axis=-1)
                predicted_patch = model.generate(input_plan.unsqueeze(0),
                                                 temp_input_patches.unsqueeze(0),
                                                 top_k=TOP_K,
                                                 top_p=TOP_P,
                                                 temperature=TEMPERATURE)
                predicted_patch = [ord(c) for c in '[r:0/'] + predicted_patch
            if predicted_patch[0] == patchilizer.bos_token_id and predicted_patch[1] == patchilizer.eos_token_id:
                end_flag = True
                break
            next_patch = patchilizer.decode([predicted_patch])

            for char in next_patch:
                byte_list.append(char)
                print(char, end='')

            patch_end_flag = False
            for j in range(len(predicted_patch)):
                if patch_end_flag:
                    predicted_patch[j] = patchilizer.special_token_id
                if predicted_patch[j] == patchilizer.eos_token_id:
                    patch_end_flag = True

            predicted_patch = torch.tensor([predicted_patch], device=device)  # (1, 16)
            input_patches = torch.cat([input_patches, predicted_patch], dim=1)  # (1, 16 * patch_len)

            if len(byte_list) > 102400:  
                failure_flag = True
                break
            if time.time() - start_time > 20 * 60:  
                failure_flag = True
                break

            if input_patches.shape[1] >= PATCH_LENGTH * PATCH_SIZE and not end_flag:
                print('Stream generating...')
                abc_code = ''.join(byte_list)
                abc_lines = abc_code.split('\n')

                tunebody_index = None
                for i, line in enumerate(abc_lines):
                    if line.startswith('[r:') or line.startswith('[V:'):
                        tunebody_index = i
                        break
                if tunebody_index is None or tunebody_index == len(abc_lines) - 1:
                    break

                metadata_lines = abc_lines[:tunebody_index]
                tunebody_lines = abc_lines[tunebody_index:]

                metadata_lines = [line + '\n' for line in metadata_lines]
                if not abc_code.endswith('\n'):  
                    tunebody_lines = [tunebody_lines[i] + '\n' for i in range(len(tunebody_lines) - 1)] + [
                        tunebody_lines[-1]]
                else:
                    tunebody_lines = [tunebody_lines[i] + '\n' for i in range(len(tunebody_lines))]

                if cut_index is None:
                    cut_index = len(tunebody_lines) // 2

                abc_code_slice = ''.join(metadata_lines + tunebody_lines[-cut_index:])
                input_patches = patchilizer.encode_generate(abc_code_slice)

                input_patches = [item for sublist in input_patches for item in sublist]
                input_patches = torch.tensor([input_patches], device=device)
                input_patches = input_patches.reshape(1, -1)

        if not failure_flag:
            generation_time_cost = time.time() - start_time

            abc_text = ''.join(byte_list)
            filename = time.strftime("%Y%m%d-%H%M%S") + \
                    "_" + format(generation_time_cost, '.2f') + '_' + str(file_no) + ".abc"
                    
            # unreduce
            unreduced_output_path = os.path.join(INTERLEAVED_OUTPUT_FOLDER, filename)
            
            abc_lines = abc_text.split('\n')
            abc_lines = list(filter(None, abc_lines))
            abc_lines = [line + '\n' for line in abc_lines]
            try:
                abc_lines = rest_unreduce(abc_lines)

                with open(unreduced_output_path, 'w') as file:
                    file.writelines(abc_lines)
            except:
                pass
            else:
                # original
                original_output_path = os.path.join(ORIGINAL_OUTPUT_FOLDER, filename)
                with open(original_output_path, 'w') as w:
                    w.write(abc_text)

                file_no += 1

        else:
            print('failed')



if __name__ == '__main__':

    plan = """
Genre: classical

Instruments: Piano, Voice

Measure: 1
  Instruments: Piano
  Pitch Range: 37–69
  Note Density: 4.0
  Tempo: 100 BPM
  Time Signature: 4/4
  Key Signature: -5
  Chords: [1, 5, 8], [1, 5], [1, 8]

Measure: 2
  Instruments: Piano
  Pitch Range: 37–70
  Note Density: 4.0
  Tempo: 100 BPM
  Time Signature: 4/4
  Key Signature: -5
  Chords: [6, 10, 1], [6, 10], [6, 1]

Measure: 3
  Instruments: Piano, Voice
  Pitch Range: 37–73
  Note Density: 5.0
  Tempo: 100 BPM
  Time Signature: 4/4
  Key Signature: -5
  Chords: [8, 0, 3], [8], [0], [3, 8]

Measure: 4
  Instruments: Piano, Voice
  Pitch Range: 37–73
  Note Density: 4.0
  Tempo: 100 BPM
  Time Signature: 4/4
  Key Signature: -5
  Chords: [1, 5, 8], [5], [1]

Measure: 5
  Instruments: Piano, Voice
  Pitch Range: 38–75
  Note Density: 5.0
  Tempo: 100 BPM
  Time Signature: 4/4
  Key Signature: -5
  Chords: [10, 1, 5], [10], [5], [1, 10]

Measure: 6
  Instruments: Piano, Voice
  Pitch Range: 35–73
  Note Density: 5.0
  Tempo: 100 BPM
  Time Signature: 4/4
  Key Signature: -5
  Chords: [3, 6, 10], [3], [6], [10]

Measure: 7
  Instruments: Piano, Voice
  Pitch Range: 35–77
  Note Density: 6.0
  Tempo: 100 BPM
  Time Signature: 4/4
  Key Signature: -5
  Chords: [8, 0, 3], [0], [3, 6, 8], [8]

Measure: 8
  Instruments: Piano, Voice
  Pitch Range: 37–73
  Note Density: 4.0
  Tempo: 100 BPM
  Time Signature: 4/4
  Key Signature: -5
  Chords: [1, 5, 8], [1]

Measure: 9
  Instruments: Piano, Voice
  Pitch Range: 33–77
  Note Density: 5.0
  Tempo: 100 BPM
  Time Signature: 4/4
  Key Signature: -5
  Chords: [6, 10, 1], [10], [1], [6]

Measure: 10
  Instruments: Piano, Voice
  Pitch Range: 33–77
  Note Density: 6.0
  Tempo: 100 BPM
  Time Signature: 4/4
  Key Signature: -5
  Chords: [8, 0, 3, 6], [0], [3], [8]

Measure: 11
  Instruments: Piano, Voice
  Pitch Range: 37–78
  Note Density: 5.0
  Tempo: 100 BPM
  Time Signature: 4/4
  Key Signature: -5
  Chords: [5, 8, 0], [5], [0], [5, 8]

Measure: 12
  Instruments: Piano, Voice
  Pitch Range: 38–77
  Note Density: 5.0
  Tempo: 100 BPM
  Time Signature: 4/4
  Key Signature: -5
  Chords: [10, 1, 5], [10], [1], [5]

Measure: 13
  Instruments: Piano, Voice
  Pitch Range: 35–77
  Note Density: 6.0
  Tempo: 100 BPM
  Time Signature: 4/4
  Key Signature: -5
  Chords: [3, 6, 10], [3, 10], [6]

Measure: 14
  Instruments: Piano, Voice
  Pitch Range: 35–77
  Note Density: 6.0
  Tempo: 100 BPM
  Time Signature: 4/4
  Key Signature: -5
  Chords: [8, 0, 3], [8, 3], [0]

Measure: 15
  Instruments: Piano, Voice
  Pitch Range: 37–80
  Note Density: 7.0
  Tempo: 100 BPM
  Time Signature: 4/4
  Key Signature: -5
  Chords: [1, 5, 8], [8, 0, 3, 6], [0]

Measure: 16
  Instruments: Piano, Voice
  Pitch Range: 37–77
  Note Density: 4.0
  Tempo: 100 BPM
  Time Signature: 4/4
  Key Signature: -5
  Chords: [1, 5, 8], [1]

Measure: 17
  Instruments: Piano, Voice
  Pitch Range: 37–80
  Note Density: 7.0
  Tempo: 100 BPM
  Time Signature: 4/4
  Key Signature: -5
  Chords: [1, 5, 8, 0], [1], [5], [8]

Measure: 18
  Instruments: Piano, Voice
  Pitch Range: 33–80
  Note Density: 7.0
  Tempo: 100 BPM
  Time Signature: 4/4
  Key Signature: -5
  Chords: [3, 6, 10], [3, 6], [10, 3]

Measure: 19
  Instruments: Piano, Voice
  Pitch Range: 35–82
  Note Density: 7.0
  Tempo: 100 BPM
  Time Signature: 4/4
  Key Signature: -5
  Chords: [8, 0, 3], [8], [0, 3, 8], [3]

Measure: 20
  Instruments: Piano, Voice
  Pitch Range: 38–80
  Note Density: 6.0
  Tempo: 100 BPM
  Time Signature: 4/4
  Key Signature: -5
  Chords: [10, 1, 5], [10], [1, 5]

Measure: 21
  Instruments: Piano, Voice
  Pitch Range: 33–82
  Note Density: 8.0
  Tempo: 100 BPM
  Time Signature: 4/4
  Key Signature: -5
  Chords: [6, 10, 1], [6], [10], [1, 6]

Measure: 22
  Instruments: Piano, Voice
  Pitch Range: 37–82
  Note Density: 7.0
  Tempo: 100 BPM
  Time Signature: 4/4
  Key Signature: -5
  Chords: [1, 5, 8], [1, 5], [8]

Measure: 23
  Instruments: Piano, Voice
  Pitch Range: 35–84
  Note Density: 8.0
  Tempo: 100 BPM
  Time Signature: 4/4
  Key Signature: -5
  Chords: [3, 6, 10, 0], [3], [6], [10]

Measure: 24
  Instruments: Piano, Voice
  Pitch Range: 35–85
  Note Density: 8.0
  Tempo: 100 BPM
  Time Signature: 4/4
  Key Signature: -5
  Chords: [8, 0, 3, 6], [8], [0], [3]

Measure: 25
  Instruments: Piano, Voice
  Pitch Range: 37–82
  Note Density: 6.0
  Tempo: 100 BPM
  Time Signature: 4/4
  Key Signature: -5
  Chords: [1, 5, 8], [1], [5], [8, 1]

Measure: 26
  Instruments: Piano, Voice
  Pitch Range: 33–80
  Note Density: 5.0
  Tempo: 100 BPM
  Time Signature: 4/4
  Key Signature: -5
  Chords: [6, 10, 1], [6], [10]

Measure: 27
  Instruments: Piano, Voice
  Pitch Range: 37–78
  Note Density: 6.0
  Tempo: 100 BPM
  Time Signature: 4/4
  Key Signature: -5
  Chords: [1, 5, 8], [5], [1, 8]

Measure: 28
  Instruments: Piano, Voice
  Pitch Range: 35–77
  Note Density: 5.0
  Tempo: 100 BPM
  Time Signature: 4/4
  Key Signature: -5
  Chords: [8, 0, 3], [8], [3]

Measure: 29
  Instruments: Piano, Voice
  Pitch Range: 37–73
  Note Density: 4.0
  Tempo: 100 BPM
  Time Signature: 4/4
  Key Signature: -5
  Chords: [1, 5, 8], [1], [5]

Measure: 30
  Instruments: Piano
  Pitch Range: 25–69
  Note Density: 3.0
  Tempo: 100 BPM
  Time Signature: 4/4
  Key Signature: -5
  Chords: [1, 5, 8], [1]
"""

    inference_patch(plan, [], 1)
