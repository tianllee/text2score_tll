from text2music.data.utils.xml2plan import get_partial_plan_text, get_full_plan_text

filepath = "/data/scratch/eey549/ABC_Dataset/ABC_Dataset/SymphonyNet_Dataset_MXL_abci/outputs/5334345.pkl"

full_plan = get_full_plan_text(filepath)
print("Full Plan:")
print(full_plan)

# Write full plan to a text file
with open("/data/home/acw769/text2score/text2music/notebooks/full_plan.txt", "w", encoding="utf-8") as f:
    f.write(full_plan)

partial_plan = get_partial_plan_text(filepath)
print("\nPartial Plan:")
print(partial_plan)

# Write partial plan to a text file
with open("/data/home/acw769/text2score/text2music/notebooks/partial_plan.txt", "w", encoding="utf-8") as f:
    f.write(partial_plan)