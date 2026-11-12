# Tamil News Reader (தமிழ் செய்தி வாசிப்பு)

A simple website that reads today's important news aloud in Tamil, section by section,
from the newspaper you choose (Dinamalar, Daily Thanthi, Dinamani, Hindu Tamil, Maalaimalar, BBC Tamil).

Sections: top headlines, Tamil Nadu, your city, India, world, sports, business / gold price, cinema.

## How it works

- `.github/workflows/deploy.yml` runs every ~3 hours (first run 6:00 AM IST).
- `scripts/build.py` collects each paper's latest headlines from Google News (filtered to that paper's site),
  records each headline as Tamil speech with Microsoft Edge's neural voice (`ta-IN-PallaviNeural`),
  and writes `site/data/news.json` plus MP3 clips.
- The `site/` folder is deployed to GitHub Pages. If a clip is missing, the page falls back to the
  device's own Tamil voice.

To change papers, sections, or cities, edit the lists at the top of `scripts/build.py`.
To refresh right now: Actions tab → "Fetch news and deploy" → Run workflow.
