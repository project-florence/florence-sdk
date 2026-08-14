# TODO

## PyPI Yayını (kullanıcı sonra halledecek — 2026-08-14 notu)

Paketleme hazır ve doğrulandı: `uv build` → sdist + wheel; `pip install <wheel>` ve
`uv add "florence-sdk @ file://..."` test edildi. Yayın için kalanlar:

- [ ] `uv publish` (PyPI token gerekli) — veya `twine upload dist/*`
- [ ] Sürüm yönetimi kararı: 0.1.0 alpha mı, 0.2.0 mı? (CLI+MCP eklendi — 0.2.0 önerilir)
- [ ] `[news]` extra kararı: trafilatura opsiyonel bağımlılık yayına dahil mi? (helpers-design.md K1)
- [ ] MCP ayrı paket kararı: florence-mcp ayrı PyPI dağıtımı olarak mı yayınlanacak? (kullanıcı kararı "paket başka olsun" — şu an tek pakette)
- [ ] README'ye PyPI badge'leri (sürüm, lisans, python)
- [ ] CI publish workflow (opsiyonel: GitHub Actions ile tag → publish)

## Diğer açık maddeler

- [ ] Helpers v1 onayı: trafilatura [news] extra + ayrı `fl helper` grubu (helpers-design.md)
- [ ] TUI implementasyonu (tui-design.md + kararlar K1-K5)
- [ ] `fl tui` komut kaydı
- [ ] api-spec / florence-sdk / florence-skill repolarının push'u
- [ ] florence-skill reposu içeriği (SKILL.md'ler — CLI/MCP oturunca)
- [ ] TS SDK / Node paketi (banner + Node TUI fikirleri oraya — research-banner-tui.md)
