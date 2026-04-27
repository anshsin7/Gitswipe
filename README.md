# GitSwipe

A Tinder-style web app for discovering GitHub developers. Describe who you want to meet, and GitSwipe finds real profiles, scores each one with AI, and lets you swipe through them — with a personalized connection message generated for every match.

![GitSwipe](https://img.shields.io/badge/built%20with-Flask%20%2B%20Groq-7c3aed?style=flat-square) ![GitHub API](https://img.shields.io/badge/data-GitHub%20API-161b22?style=flat-square&logo=github)

## Demo

Type your criteria in plain English:
```
Works in AI / machine learning
Based in Zurich or studying at ETH
Open source contributor
Has >500 GitHub followers
```

GitSwipe searches GitHub, scores each profile 0–100 against your criteria, and shows you a swipeable card with:
- their avatar, bio, location, and follower count
- top 3 public repos (name, stars, language)
- an AI-generated summary and reasons for the score
- a personalized connection message on every match

Swipe right (or press `Y`) to save a match. Swipe left (or press `N`) to skip.

## Quickstart

**1. Clone and install**
```bash
git clone https://github.com/YOUR_USERNAME/gitswipe.git
cd gitswipe
pip install -r requirements.txt
```

**2. Set your API keys**
```bash
cp .env.example .env
# Edit .env and fill in your keys
```

| Key | Where to get it | Free? |
|-----|----------------|-------|
| `GROQ_API_KEY` | [console.groq.com/keys](https://console.groq.com/keys) | Yes |
| `GITHUB_TOKEN` | [github.com/settings/tokens](https://github.com/settings/tokens) — no permissions needed | Yes |

> Without a GitHub token you get 60 API requests/hour. With one: 5,000/hr.

**3. Run**
```bash
python3 app.py
```

Opens automatically at [http://localhost:5000](http://localhost:5000).

## How it works

1. Your criteria are sent to the LLM, which converts them into a GitHub user search query
2. The top 30 matching users are fetched from the GitHub API
3. For each profile, the app fetches their bio + top repos and asks the LLM to score the fit
4. You swipe through the cards — matches and their connection notes are saved to `accepted_profiles.json`

## Controls

| Action | Key / gesture |
|--------|--------------|
| Connect | `Y`, `→`, swipe right, or click ✓ |
| Skip | `N`, `←`, swipe left, or click ✕ |

## Requirements

- Python 3.10+
- Groq API key (free)
- GitHub personal access token (free, no permissions needed)
