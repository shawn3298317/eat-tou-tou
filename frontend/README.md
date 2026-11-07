# Taipei Eats — frontend (Next.js)

## Run

```bash
npm install
npm run dev      # http://localhost:3000
```

The frontend talks to the FastAPI backend on `http://localhost:8000` by
default. Override with `NEXT_PUBLIC_API_URL`:

```bash
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev
```

Build for production: `npm run build` then `npm start`.

## Features

- Instant search box (debounced) hitting `GET /api/search` — FTS5 + CJK
  substring search on the backend.
- Conditional filters: cuisine chips, district, price band, top-N.
- “Top cuisines by community response” strip from
  `GET /api/cuisines/top` — cuisine types ranked by thread mentions; click
  one to filter by it.
- Ranked cards with the score breakdown, price range, MRT, must-try dish
  and a Google Maps link.
- Add-a-restaurant form — appends a row to `data/restaurants.csv` via the API.
