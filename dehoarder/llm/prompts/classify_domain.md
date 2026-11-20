You are classifying a website for a personal book catalogue.

The operator has browser tabs open on the domain `{{ domain }}`. Here are up to
ten of those tabs, as URL and page title:

{{ samples }}

Decide whether this domain is a place where books are sold or published:
a bookshop, a publisher's own site, or a marketplace whose listings here are
books. Blogs, reviews, libraries, wikis, news and social sites are **not**
bookshops, even when they talk about books.

Answer with JSON only:

- `is_bookshop`: true if the domain sells or publishes books and these tabs are book pages.
- `shop_name`: the shop's human-readable name as the site presents it (e.g. "Labirint", "Éditions Gallimard"), or the domain if unclear.
- `kind`: `bookshop`, `publisher`, or `marketplace`. Use `bookshop` when `is_bookshop` is false.
- `confidence`: a number from 0 to 1.

Example:

{"is_bookshop": true, "shop_name": "Labirint", "kind": "bookshop", "confidence": 0.9}
