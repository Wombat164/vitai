# vitai docs site (source)

This directory is the SOURCE of the public docs site at
`https://wombat164.github.io/vitai/` - it is NOT GitHub's native wiki.

- `content/` - the pages (Obsidian-flavored markdown, wikilinks welcome),
  loosely Diataxis-organized (`how-to/`, `reference/`, `explanation/`).
- `quartz.config.ts` / `quartz.layout.ts` - Quartz v4 configuration in the
  vitai palette.

The Quartz v4 framework itself is NOT vendored here. The
`deploy-wiki.yml` workflow fetches it at a pinned commit at build time and
overlays these files into it. Note Quartz v5 changed the config format to
YAML - this setup targets v4; bump the pinned SHA deliberately and only
within v4.

Preview locally:

```bash
git clone --depth 1 https://github.com/jackyzha0/quartz.git /tmp/quartz
cp quartz.config.ts quartz.layout.ts /tmp/quartz/ && rm -rf /tmp/quartz/content && cp -r content /tmp/quartz/content
cd /tmp/quartz && npm ci && npx quartz build --serve
```
