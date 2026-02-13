import os

# Configurations for inference
INFERENCE_WEIGHTS_PATH = '/data/home/acw769/text2score/weights_notagen_finetune_p_size_16_p_length_2048_p_layers_20_c_layers_6_h_size_768_lr_0.0001_batch_16.pth'               # Path to weights for inference# Folder to save output files
# INFERENCE_WEIGHTS_PATH = '/data/home/acw769/text2score/weights_notagen_pretrain_p_size_16_p_length_2048_p_layers_16_c_layers_3_h_size_768_lr_0.0001_batch_8.pth'               # Path to weights for inference
NUM_SAMPLES = 1                                               # Number of samples to generate (only for generate mode)
TOP_K = 9                                                       # Top k for sampling
TOP_P = 0.9                                                      # Top p for sampling
TEMPERATURE = 1.2                                                 # Temperature for sampling
ORIGINAL_OUTPUT_FOLDER = os.path.join('./text2music/artifacts/output/original', os.path.splitext(os.path.split(INFERENCE_WEIGHTS_PATH)[-1])[0] + '_k_' + str(TOP_K) + '_p_' + str(TOP_P) + '_temp_' + str(TEMPERATURE))
INTERLEAVED_OUTPUT_FOLDER = os.path.join('./text2music/artifacts/output/interleaved', os.path.splitext(os.path.split(INFERENCE_WEIGHTS_PATH)[-1])[0] + '_k_' + str(TOP_K) + '_p_' + str(TOP_P) + '_temp_' + str(TEMPERATURE))
XML_OUTPUT_FOLDER = os.path.join('./text2music/artifacts/output/xml', os.path.splitext(os.path.split(INFERENCE_WEIGHTS_PATH)[-1])[0] + '_k_' + str(TOP_K) + '_p_' + str(TOP_P) + '_temp_' + str(TEMPERATURE))

# Configurations for model
PATCH_STREAM = True                                             # Stream training / inference
PATCH_SIZE = 16                                                # Patch Size
PATCH_LENGTH = 2048                                             # Patch Length
CHAR_NUM_LAYERS = 6                                             # Number of layers in the decoder
PATCH_NUM_LAYERS = 20                                           # Number of layers in the encoder
HIDDEN_SIZE = 768                                               # Hidden Size