import matplotlib.font_manager as fm

# 将所有Matplotlib能找到的字体都写入文件
font_list = sorted([f.name for f in fm.fontManager.ttflist])

with open("font_list.txt", "w", encoding="utf-8") as f:
    for font_name in font_list:
        f.write(font_name + "\n")

print("所有可用字体已写入 font_list.txt 文件。")
print("请打开该文件，从中找一个看起来是中文的字体名称（例如包含 'Hei', 'Song', 'Kai', 'Yuan' 等字样）。")