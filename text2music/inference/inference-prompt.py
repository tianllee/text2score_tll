
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
from groq import Groq
import argparse

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

def get_inference_plan(user_prompt: str, api_key: str) -> str:

    prompt = """
    You are an assistant music composer that creates structured musical plans based on user descriptions. Your task is to convert the user’s prompt into a measure-wise musical plan that will be fed to a Generative AI model. Instead of a full list of consecutive measures, your task is to generate a more concise plan for the piece based on measures which have significant change. This could be for example in tempo, time and key signature, instrumentation, note density and pitch range.

    At the top, you need to specify the total number of measures in the entire piece. If this is not indicated by the user, a good number may be around 30 measures. Then, you may specify a genre only if explicitly asked in the user's prompt and if it matches the available genres which are as follows: symphony, classical piano, classical, jazz, pop, rock, metal and folk. Following this, you must specify all the instruments present in the piece.

    Then, each measure in the plan should be described using the following fields:
    Instruments: The instruments used (e.g., Piano, Trombone, Voice). We can use all MuseScore instrument names and also voice.
    Pitch Range: Lowest to highest MIDI note number of the measure, summarized for all instruments as a range. Think about the lowest and highest pitch range of each instrument when calculating this range. Please use a diverse (but realistic) pitch range for every measure.
    Note Density: Average number of notes per instrument in the measure, summarized for all instruments as a single number. The note density value should consider the total elements in the chord list along with the time signature. For example, a note density of 4 in a time signature of 4/4 may be perceived as few notes whereas a value of 16 may be a lot of notes.
    Time Signature: Standard Notation (e.g., 3/4, 4/4, 6/8)
    Key Signature: Number of sharps/flats (e.g., -5 for 5 flats, 2 for 2 sharps). Do not include the mode.
    Chords: These are not just lists of chord notes but also arpeggios, standalone note pitches as well as appoggiatura and acciaccatura, each expressed as a list of **unique** MIDI pitches % 12 (e.g., [9, 2], [2], [2, 6, 8, 9, 11]). They can be single or multiple elements within a list, denoting a single note or multiple notes played within a short duration of time. You may use the these to steer the musical mode (major / minor). **Please use extremely diverse and variable length elements to denote chords / arpeggios / note pitches / grace notes**.
    You are allowed and expected to change these musical attributes in the plan as needed to reflect the musical mood, instrumentation, style and musical structure.

    You may generate around 10 structurally important measures with their measure numbers. The measures do not need to be consecutive always but they could be depending on the scope of the user’s description. However, the measure numbers should be lesser than equal to the total measures asked for at the top of the plan.

    Use the following format for the global information:
    Total Measures: <number>
    Genre: <string> (Only if indicated and matches with available genres. Otherwise, skip it.)
    Instruments: <list>

    Use the following format for each measure:
    Measure: <number>
    Instruments: <list>
    Pitch Range: <min>–<max>
    Note Density: <float>
    Tempo: <int> BPM
    Time Signature: <string> (e.g., 3/4, 4/4, 6/8)
    Key Signature: <int> (e.g. -5 for 5 flats, 2 for 2 sharps)
    Chords: [<midi pitch number % 12>, <midi pitch number % 12>], [<midi pitch number % 12>, <midi pitch number % 12>, <midi pitch number % 12>], ...

    For each measure, every attribute (e.g., 'Instruments:', 'Pitch Range:', 'Note Density:', etc.) must start in a new line, exactly as shown in the example plan below. Always add an empty line before starting a new 'Measure: <number>' line. Avoid natural language explanation or additional commentary and follow the output format exactly.

    Here is an example of a plan for the prompt "Short eerie symphonic music in 4/4 time signature with a moderate tempo":

    Total Measures: 29

    Genre: symphony

    Instruments: Trombone, Timpani, Cymbal, Maracas, Saw Synthesizer, Pan Flute, Violins

    Measure: 1
    Instruments: Violins, Saw Synthesizer
    Pitch Range: 43–66
    Note Density: 2.0
    Tempo: 124 BPM
    Time Signature: 4/4
    Chords: [0, 2, 6, 7]

    Measure: 2
    Instruments: Violins, Pan Flute, Trombone, Saw Synthesizer
    Pitch Range: 24–67
    Note Density: 4.25
    Tempo: 124 BPM
    Time Signature: 4/4
    Chords: [0, 3, 7], [0], [0, 3, 7], [0]

    Measure: 14
    Instruments: Violins, Saw Synthesizer, Timpani
    Pitch Range: 24–84
    Note Density: 6.0
    Tempo: 124 BPM
    Time Signature: 4/4
    Chords: [0], [0], [0], [0]

    Measure: 15
    Instruments: Violins, Saw Synthesizer, Timpani
    Pitch Range: 24–84
    Note Density: 6.333333333333333
    Tempo: 124 BPM
    Time Signature: 4/4
    Chords: [0], [0], [0], [0]

    Measure: 16
    Instruments: Violins, Pan Flute, Trombone, Saw Synthesizer
    Pitch Range: 24–67
    Note Density: 4.25
    Tempo: 124 BPM
    Time Signature: 4/4
    Chords: [0, 3, 7], [0], [0, 3, 7], [0]

    Measure: 17
    Instruments: Violins, Pan Flute, Trombone, Saw Synthesizer
    Pitch Range: 24–66
    Note Density: 4.75
    Tempo: 124 BPM
    Time Signature: 4/4
    Chords: [0, 2, 6], [0], [0, 2, 6], [0, 3]

    Measure: 28
    Instruments: Violins, Saw Synthesizer, Timpani
    Pitch Range: 24–84
    Note Density: 6.0
    Tempo: 124 BPM
    Time Signature: 4/4
    Chords: [0], [0], [0], [0]

    Now, here's the user's prompt:

    User:
    {user_prompt}

    Assistant:
    """.format(user_prompt=user_prompt)

    client = Groq(api_key=api_key)

    completion = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[{"role": "user", "content": prompt}],
        temperature=1.0,
        max_completion_tokens=8192,
        top_p=0.95,
        reasoning_effort="high",
        stream=False,
        stop=None
    )

    plan = completion.choices[0].message.content

    return plan



if __name__ == '__main__':

    # Define args
    parser = argparse.ArgumentParser()
    parser.add_argument('--api_key', type=str, required=True, help='API key for Groq')
    parser.add_argument('--user_prompt', type=str, required=False, default="Vintage French Chanson: Create a nostalgic chanson piece in C major with a slow tempo. The chord progression will be C, Am, Dm, G, played over 16 bars. Utilize accordion, violin, and contrabass. The accordion should lead with its melodious and expressive sound, the violin should add a romantic and wistful quality, and the upright bass should provide a warm, supporting foundation. This composition should evoke the charm and sentimentality of a vintage French chanson.", help='User prompt for music generation')
    args = parser.parse_args()
    
    API_KEY = args.api_key
    USER_PROMPT = args.user_prompt

    plan = get_inference_plan(USER_PROMPT, API_KEY)
    print("Generated Inference Plan:\n", plan)

    inference_patch(plan, [], pieces=NUM_SAMPLES)
