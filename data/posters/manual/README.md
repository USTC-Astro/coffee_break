# 手动发布 PNG 海报

1. 在 GitHub 上打开本目录，点 **Add file → Upload files**，上传 PNG 并提交到 `main`。
2. 打开 **Actions → Publish uploaded poster → Run workflow**。
3. 填写论文 arXiv 号（例如 `2609.30441`）和 PNG 文件名（例如 `2609.30441.png`，不含目录路径）。

运行成功后，图片会出现在海报轮换中；对应论文卡片也会打开该图片。手动海报优先于同一论文的自动生成版，并会在后续自动更新时保留。上传文件本身不会自动加入轮换，需执行第 2 步。
