# bunnychung.com

Bunny Chung 個人作品集。網站喺 `docs/`，由 `build.py` 生成，GitHub Pages serve `docs/`。

## 加作品

1. 喺 `works/` 開一個新 folder，例如 `works/2025-hku-ai-avatar/`（可以 copy `works/_template`）。
2. 將作品圖片 / 影片放入去：
   - `cover.jpg`（或 .png）＝ 封面；冇嘅話用第一張圖。
   - 其他圖會按檔名排序顯示，例如 `01.jpg`、`02.jpg`。
   - 大相會自動縮細到 2000px。
   - 影片超過 50MB 建議放 YouTube / Vimeo，然後喺 `info.txt` 寫 `video: <網址>`。
3. 寫 `info.txt`：

   ```
   title: 作品名稱
   year: 2025
   category: Video          ← 用嚟做篩選
   role: Director, Editor
   client: HKU
   tags: AI, Video Editing
   order: 0                 ← 數字大嘅排前（可以唔寫）
   video: https://youtu.be/...
   link:
   ---
   作品簡介……
   ```

4. Folder 名用 `_` 開頭就唔會上網（草稿用）。

## 更新網站

```bash
python3 build.py
git add -A && git commit -m "Add work" && git push
```

## 改「關於我」、聯絡方法

直接改 `src/index.html`（`EXPERIENCE`、`EDUCATION`、`.skills`、`About me` 段落）。唔好改 `docs/`，每次 build 會覆蓋。
