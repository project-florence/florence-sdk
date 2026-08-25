"""Tool envanteri meta verisi: isim, grup, LLM aciklamasi, risk isaretleri.

mcp-design.md Bölüm 2'nin makine-okunur hali: her tool'un adi (CLI uyumlu),
domain grubu (``MCP_DISABLE_GROUPS`` filtresi), LLM icin aciklama ve risk
isaretleri:

- ``danger``  -> 🔴 DANGER (kalici/kritik yan etki; onay onerilir)
- ``credit``  -> 🟠 CREDIT (kredi harcar; maliyet aciklamada)
- ``write``   -> 🟡 WRITE (veri yazar; idempotent/geri alinabilir)
- ``confirm`` -> ekstra zorunlu ``confirm: bool`` parametresi (savunma hatti,
  mcp-design.md Bölüm 2.4): ``false`` ile cagri reddedilir.

Grup adlari CLI gruplariyla birebir: ``auth``, ``account``, ``market``,
``economy``, ``portfolio``, ``analysis``, ``bots``, ``export``, ``misc``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = [
    "GROUPS",
    "ToolSpec",
    "TOOLS",
    "enabled_specs",
    "spec_by_name",
    "specs_by_group",
]

#: Domain gruplari (CLI grup adlariyla birebir, mcp-design.md Bölüm 2.1).
GROUPS: tuple[str, ...] = (
    "auth",
    "account",
    "market",
    "economy",
    "portfolio",
    "analysis",
    "bots",
    "export",
    "misc",
    "helpers",
)


@dataclass(frozen=True)
class ToolSpec:
    """Tek MCP tool'unun meta verisi."""

    name: str
    group: str
    description: str
    danger: bool = False
    credit: bool = False
    write: bool = False
    confirm: bool = False
    tags: set[str] = field(default_factory=set)

    @property
    def marker(self) -> str:
        """Aciklamanin basina eklenecek risk isareti (bos olabilir)."""
        if self.danger:
            return "🔴 DANGER"
        if self.credit:
            return "🟠 CREDIT"
        if self.write:
            return "🟡 WRITE"
        return ""

    def llm_description(self) -> str:
        """Risk isareti ile baslayan tam LLM aciklamasi."""
        if self.marker:
            return f"{self.marker} — {self.description}"
        return self.description


def _spec(
    name: str,
    group: str,
    description: str,
    *,
    danger: bool = False,
    credit: bool = False,
    write: bool = False,
    confirm: bool = False,
    tags: set[str] | None = None,
) -> ToolSpec:
    return ToolSpec(
        name=name,
        group=group,
        description=description,
        danger=danger,
        credit=credit,
        write=write,
        confirm=confirm,
        tags=tags or set(),
    )


# ---------------------------------------------------------------------------
# 92 tool — mcp-design.md Bölüm 2.2'den birebir (isimler CLI uyumludur).
# ---------------------------------------------------------------------------
TOOLS: tuple[ToolSpec, ...] = (
    # ---- auth (10) ------------------------------------------------------
    _spec(
        "auth_login",
        "auth",
        "Kullanici adi + sifre ile oturum ac (form-encoded login). Sifre LLM "
        "baglamina girer — tercihen env/keyring ile onceden kimlik tanimlanmis "
        "olmalidir. Token'lar store'a yazilir.",
        danger=True,
    ),
    _spec(
        "auth_logout",
        "auth",
        "Mevcut oturumu kapat; refresh token'i iptal et ve store'u temizle.",
    ),
    _spec(
        "auth_register",
        "auth",
        "Yeni kullanici kaydi (public). Sifre min 10 karakter; dogrulama maili "
        "tetiklenir.",
        write=True,
    ),
    _spec(
        "auth_verify_email",
        "auth",
        "E-posta dogrulama token'ini onayla (public).",
    ),
    _spec(
        "auth_resend_verification",
        "auth",
        "Dogrulama mailini yeniden gonder (public; 3/saat limitli).",
    ),
    _spec(
        "auth_change_password",
        "auth",
        "Sifre degistir; TUM refresh token'lar iptal olur (yeniden login "
        "gerekir). Yeni sifre min 10 karakter.",
        danger=True,
    ),
    _spec(
        "auth_change_email",
        "auth",
        "E-posta degistir; tum refresh token'lar iptal olur.",
        danger=True,
    ),
    _spec(
        "auth_change_username",
        "auth",
        "Kullanici adi degistir; tum refresh token'lar iptal olur.",
        danger=True,
    ),
    _spec(
        "auth_delete_account",
        "auth",
        "Hesabi KALICI olarak siler — geri alinamaz. confirm=true zorunludur; "
        "kullanici onayi olmadan cagirma.",
        danger=True,
        confirm=True,
    ),
    _spec(
        "auth_status",
        "auth",
        "Hangi kimlikle bagli olundugunu soyler: authenticated, identity_type "
        "(user/bot/none), username, token_source (env/keyring/memory). API "
        "cagrisi yapmaz.",
    ),
    # ---- account (6; SDK: UserResource) ---------------------------------
    _spec(
        "account_profile",
        "account",
        "Profil + kredi bilgisi: username, email, user_type, email_verified, "
        "avatar, credits. Kimligi dogrulamak icin kullan.",
    ),
    _spec(
        "account_update_avatar",
        "account",
        "Avatar degistir (avatar-1 .. avatar-12).",
        write=True,
    ),
    _spec(
        "account_get_preferences",
        "account",
        "Kullanici tercihlerini oku (JSONB).",
    ),
    _spec(
        "account_update_preferences",
        "account",
        "Tercihleri guncelle; PUT mevcut prefs ile birlestirir (kismi "
        "guncelleme guvenli).",
        write=True,
    ),
    _spec(
        "account_credits",
        "account",
        "Kredi bakiyesi — kredi harcayan tool'lar oncesi/sonrasi kontrol icin.",
    ),
    _spec(
        "account_export_data",
        "account",
        "Kullanicinin tum verisinin JSON dump'i: profile, favorites, reports, "
        "token_usage, simulations.",
    ),
    # ---- market (11) ----------------------------------------------------
    _spec(
        "market_list_companies",
        "market",
        "BIST sirket listesi (public). sort: alphabetical|popular; limit <= 500.",
    ),
    _spec(
        "market_list_tickers",
        "market",
        "BIST ticker listesi (public).",
    ),
    _spec(
        "market_search_companies",
        "market",
        "Sirket ara — alias destekli (public).",
    ),
    _spec(
        "market_company_info",
        "market",
        "Tek sirketin profili (public). format='json' -> yapilandirilmis profil; "
        "format='md' -> markdown metin.",
    ),
    _spec(
        "market_companies_summary",
        "market",
        "Ozet tablo: gainers/losers/price_high/volume/market_cap siralamalari; "
        "tickers virgullu filtre (CSV).",
    ),
    _spec(
        "market_news",
        "market",
        "Hisse haberleri — news feature'i gerekir, 10/dk rate limit. amount "
        "1-50 arasi.",
        write=True,
    ),
    _spec(
        "market_price_current",
        "market",
        "Anlik fiyat/quote (public). is_stale ve change_pct: null semantigine "
        "dikkat (piyasa acikken intraday veri yoksa).",
    ),
    _spec(
        "market_price_history",
        "market",
        "Fiyat gecmisi (public; 60s cache). period 1d..max; interval 5m..3mo.",
    ),
    _spec(
        "market_status",
        "market",
        "Piyasa acik mi: {open, next_open_at, holiday} (60s cache). Islem "
        "oncesi kontrol icin.",
    ),
    _spec(
        "market_stats_top",
        "market",
        "Aktiviteye gore populer ticker'lar (public).",
    ),
    _spec(
        "market_stats",
        "market",
        "Tek ticker'in sayaclari (public). portfolio_stats ile karistirma.",
    ),
    _spec(
        "market_digest",
        "market",
        "Piyasa bülteni (morning/noon/evening slotları, tarih filtreli veya en güncel bülten).",
    ),
    # ---- economy (6) ----------------------------------------------------
    _spec(
        "economy_gold_prices",
        "economy",
        "Altin fiyatlari (16 kalem; public). Degerler STRING + Turk virgullu "
        "ondalik ('40,25') — sayisal islem oncesi ','->'.' donusumu gerekir.",
    ),
    _spec(
        "economy_silver_price",
        "economy",
        "Gumus fiyati (public).",
    ),
    _spec(
        "economy_platinum_price",
        "economy",
        "Gram platin fiyati (public).",
    ),
    _spec(
        "economy_palladium_price",
        "economy",
        "Gram paladyum fiyati (public).",
    ),
    _spec(
        "economy_currency",
        "economy",
        "Doviz kurlari (public); symbols filtresi virgullu (USD,EUR).",
    ),
    _spec(
        "economy_macroeconomy",
        "economy",
        "FRED makro serileri (14 seri, 24h cache; public).",
    ),
    # ---- portfolio (24) -------------------------------------------------
    _spec(
        "portfolio_add_favorite",
        "portfolio",
        "Favorilere ekle (idempotent).",
        write=True,
    ),
    _spec(
        "portfolio_remove_favorite",
        "portfolio",
        "Favorilerden cikar.",
        write=True,
    ),
    _spec(
        "portfolio_list_favorites",
        "portfolio",
        "Favori listesi.",
    ),
    _spec(
        "portfolio_create",
        "portfolio",
        "Sanal portfoy olustur. initial_balance > 0.",
        write=True,
    ),
    _spec(
        "portfolio_list",
        "portfolio",
        "Portfoy listesi.",
    ),
    _spec(
        "portfolio_get",
        "portfolio",
        "Tek portfoy.",
    ),
    _spec(
        "portfolio_rename",
        "portfolio",
        "Portfoyu yeniden adlandir.",
        write=True,
    ),
    _spec(
        "portfolio_delete",
        "portfolio",
        "Portfoyu sil — islemler dahil KALICIDIR. confirm=true zorunludur.",
        write=True,
        confirm=True,
    ),
    _spec(
        "portfolio_duplicate",
        "portfolio",
        "Portfoyu islemleriyle kopyala.",
        write=True,
    ),
    _spec(
        "portfolio_list_transactions",
        "portfolio",
        "Islem listesi; filtreler: ticker, tx_type (BUY/SELL), start/end ISO.",
    ),
    _spec(
        "portfolio_add_transaction",
        "portfolio",
        "Islem ekle — piyasa ACIK olmali (kapaliysa 400 'Market is closed'); "
        "fiyat piyasadan otomatik alinir, komisyon isler.",
        write=True,
    ),
    _spec(
        "portfolio_update_transaction",
        "portfolio",
        "Islemi guncelle (manuel fiyat/miktar; en az biri). Piyasa-acik "
        "kontrolunden muaftir.",
        write=True,
    ),
    _spec(
        "portfolio_undo_transaction",
        "portfolio",
        "Son islemi geri al. confirm=true zorunludur.",
        write=True,
        confirm=True,
    ),
    _spec(
        "portfolio_valuation",
        "portfolio",
        "Degerleme: total_value, pnl, varlik kirilimi.",
    ),
    _spec(
        "portfolio_diversification",
        "portfolio",
        "Cesitlendirme (stock/forex/metal dagilimi).",
    ),
    _spec(
        "portfolio_performers",
        "portfolio",
        "En iyi/en kotu hisseler.",
    ),
    _spec(
        "portfolio_history",
        "portfolio",
        "Deger gecmisi. period: 1w/1mo/3mo/6mo/1y/max.",
    ),
    _spec(
        "portfolio_returns",
        "portfolio",
        "Getiri (abs/total/CAGR).",
    ),
    _spec(
        "portfolio_risk",
        "portfolio",
        "Risk: volatility, max_drawdown, sharpe.",
    ),
    _spec(
        "portfolio_benchmark",
        "portfolio",
        "XU100 karsilastirma (default ticker XU100).",
    ),
    _spec(
        "portfolio_performance",
        "portfolio",
        "Verimlilik skoru.",
    ),
    _spec(
        "portfolio_stats",
        "portfolio",
        "Islem istatistikleri. market_stats ile karistirma.",
    ),
    _spec(
        "portfolio_snapshot",
        "portfolio",
        "Birlesik ozet (hizli genel bakis icin).",
    ),
    _spec(
        "portfolio_export_csv",
        "portfolio",
        "Portfoy islemlerini CSV olarak indir — ham CSV metni doner (JSON degil).",
    ),
    # ---- analysis (13) --------------------------------------------------
    _spec(
        "analysis_per_day_cost",
        "analysis",
        "Gunluk simulasyon maliyeti (0.005 kredi/gun). Maliyet hesaplamak icin "
        "once bunu oku.",
    ),
    _spec(
        "analysis_estimate_cost",
        "analysis",
        "Simulasyon maliyet tahmini (days 1..370).",
    ),
    _spec(
        "analysis_list_simulations",
        "analysis",
        "Simulasyon gecmisi (limit <= 100).",
    ),
    _spec(
        "analysis_get_simulation",
        "analysis",
        "Tek simulasyon detayi (sonuc JSONB dahil).",
    ),
    _spec(
        "analysis_simulate",
        "analysis",
        "Monte Carlo simulasyonu CALISTIRIR — maliyet = gun x 0.005 kredi "
        "(once account_credits / analysis_estimate_cost ile bakiyeyi kontrol "
        "et). Job-slot 600s. days 1..370.",
        credit=True,
    ),
    _spec(
        "analysis_generate_report",
        "analysis",
        "Rapor URETIR — kredi harcar (quick ~0.25, deep daha fazla; tahsilat "
        "token bazli). 90 saniyeye kadar surebilir (job-slot 900s). Once "
        "account_credits ile bakiyeyi kontrol et; kesilirse "
        "analysis_list_reports / analysis_get_report ile kurtar.",
        credit=True,
    ),
    _spec(
        "analysis_report_info",
        "analysis",
        "Rapor maliyetleri + endpoint dokumantasyonu. Kredi harcamadan once oku.",
    ),
    _spec(
        "analysis_list_reports",
        "analysis",
        "Rapor gecmisi (sort/order allowlist'li).",
    ),
    _spec(
        "analysis_search_reports",
        "analysis",
        "Raporda ara (q baslik/icerik ILIKE).",
    ),
    _spec(
        "analysis_get_report",
        "analysis",
        "Tek rapor (owner-only; markdown icerik dahil rapor objesi).",
    ),
    _spec(
        "analysis_download_report",
        "analysis",
        "Raporu indir: ftype md/docx/pdf. dest_path verilirse dosya sunucuya "
        "yazilir ve yol doner; verilmezse md metin, binary'ler base64 doner.",
    ),
    _spec(
        "analysis_fit_stocks",
        "analysis",
        "Profil kriterlerine gore hisse eslestir (advisor feature'i gerekir).",
    ),
    _spec(
        "analysis_portfolio_profile",
        "analysis",
        "Portfoye benzer hisseler (Euclidean; ticker'lar buyuk harfe cevrilir).",
    ),
    # ---- bots (3) -------------------------------------------------------
    _spec(
        "bots_create",
        "bots",
        "Bot hesabi olustur (max 5/kullanici). Yanittaki password TEK "
        "SEFERLIKTIR ve ciktiya GIRMEZ (*** maskeli; store'a yazilir).",
        write=True,
    ),
    _spec(
        "bots_list",
        "bots",
        "Kendi botlarini listele.",
    ),
    _spec(
        "bots_delete",
        "bots",
        "Botu sil (owner-only; kalici; store'daki sifresi de temizlenir). "
        "confirm=true zorunludur.",
        write=True,
        confirm=True,
    ),
    # ---- export (5) -----------------------------------------------------
    _spec(
        "export_create",
        "export",
        "Export siparisi ver (202, idempotent: ayni user+year+format aktif "
        "kaydi varsa mevcut id doner; 3/saat limit).",
        write=True,
    ),
    _spec(
        "export_status",
        "export",
        "Tek export kaydi durumu (owner-only). Status: queued/processing/"
        "ready/sent/error.",
    ),
    _spec(
        "export_list",
        "export",
        "Export kayitlari listesi.",
    ),
    _spec(
        "export_wait",
        "export",
        "Export ready/sent olana kadar POLL eder (bloklar). timeout asilirsa "
        "hata; export_status ile tekrar sorgula.",
    ),
    _spec(
        "export_download",
        "export",
        "Public token ile indir (auth gerekmez; gzip). token_or_url ham token "
        "veya download_url olabilir. dest_path verilirse sunucuya yazilir, "
        "yol doner; yoksa base64.",
    ),
    # ---- misc (14) ------------------------------------------------------
    _spec(
        "misc_ipos_upcoming",
        "misc",
        "Yaklasan halka arzlar (public).",
    ),
    _spec(
        "misc_ipos_draft",
        "misc",
        "Taslak halka arzlar (public).",
    ),
    _spec(
        "misc_ipos_active",
        "misc",
        "Aktif halka arzlar (public).",
    ),
    _spec(
        "misc_ipo_detail",
        "misc",
        "Tek halka arz detayi (yoksa 404).",
    ),
    _spec(
        "misc_legal",
        "misc",
        "Tek politika metni: terms/privacy_policy/cookie_policy/disclaimer "
        "(public).",
    ),
    _spec(
        "misc_legal_all",
        "misc",
        "Tum politikalar (public).",
    ),
    _spec(
        "misc_about",
        "misc",
        "Platform hakkinda metni (public).",
    ),
    _spec(
        "misc_version",
        "misc",
        "API surum bilgisi (public).",
    ),
    _spec(
        "misc_contact",
        "misc",
        "Iletisim bilgileri (public).",
    ),
    _spec(
        "misc_contributors",
        "misc",
        "Katkida bulunanlar (public).",
    ),
    _spec(
        "misc_maintenance",
        "misc",
        "Devre disi ozellik listesi — bir tool 503 donerse once bunu kontrol et.",
    ),
    _spec(
        "misc_health",
        "misc",
        "API saglik kontrolu (public; {status: ok}). market_status ile "
        "karistirma (piyasa acik/kapali != API sagligi).",
    ),
    _spec(
        "misc_announcements",
        "misc",
        "Son 7 gunun duyurulari (JWT).",
    ),
    _spec(
        "misc_announcement",
        "misc",
        "Tek duyuru (JWT).",
    ),
    # ---- helpers (6) — semantik kompozitler (helpers-design.md Bölüm 2/4.3) --
    # Kompozit tool'lar: endpoint'lerin ustune biner; tek niyet = tek cagri.
    # Bos/kisa sonuc disiplini: 0 haber -> bos liste (hata DEGIL); kismi
    # hata -> ilgili alanda hata kodu, paket doner. Hepsi salt-okuma.
    _spec(
        "helper_news_digest",
        "helpers",
        "Ticker'in ilk N haberinin icerikli ozeti. 1 backend + N harici HTTP "
        "istegi yapar (news 10/dk rate limiti; haber yoksa bos liste doner, "
        "hata degil). fetch_content=False ile icerik cekimi atlanir.",
    ),
    _spec(
        "helper_fetch_article",
        "helpers",
        "URL'deki makaleyi duz metin olarak ceker — SSRF korumali (sema "
        "allowlist + localhost/ozel ag engeli + her redirect atlamasinda "
        "yeniden dogrulama). 404/JS-render sonuc nesnesidir, hata degil.",
    ),
    _spec(
        "helper_ticker_briefing",
        "helpers",
        "Ticker tek bakista: fiyat + sirket profili + trend (sparkline) + son "
        "haberler. 4 backend cagrisi; eksik parcalar null doner, paket asla "
        "dusmez. 'X hissesi nasil?' sorusunun karsiligi.",
    ),
    _spec(
        "helper_market_pulse",
        "helpers",
        "Piyasa ne durumda: acik/kapali + kazananlar + kaybedenler + hacim "
        "liderleri + populerler. 5 backend cagrisi, TAMAMI public (kimlik "
        "gerekmez). Piyasa kapaliysa listeler yine doner.",
    ),
    _spec(
        "helper_portfolio_health",
        "helpers",
        "Portfoy sagligi ozeti: deger, kar/zarar, en iyi/en kotu hisseler, "
        "risk (volatility/drawdown/sharpe), XU100 benchmark, cesitlendirme. "
        "5 backend cagrisi (JWT gerekir). Tek analiz ucu basarisizsa alan "
        "null olur; portfoy yoksa hata.",
    ),
    _spec(
        "helper_macro_briefing",
        "helpers",
        "Makro manzara: doviz kurlari + altin fiyatlari + FRED makro "
        "serileri. 3 backend cagrisi (JWT gerekir). Backend string/Turk "
        "virgullu degerleri float'a normalize eder. Seri yoksa ilgili alan "
        "{} doner.",
    ),
)

#: confirm zorunlu tool'lar (mcp-design.md Bölüm 2.4 savunma hatti).
CONFIRM_REQUIRED: frozenset[str] = frozenset(
    spec.name for spec in TOOLS if spec.confirm
)

#: DANGER tool'lar (mcp-design.md Bölüm 2.1).
DANGER_TOOLS: frozenset[str] = frozenset(spec.name for spec in TOOLS if spec.danger)

#: CREDIT tool'lar (kredi harcar).
CREDIT_TOOLS: frozenset[str] = frozenset(spec.name for spec in TOOLS if spec.credit)


def spec_by_name(name: str) -> ToolSpec | None:
    """Tool adindan spec; yoksa ``None``."""
    for spec in TOOLS:
        if spec.name == name:
            return spec
    return None


def specs_by_group() -> dict[str, list[ToolSpec]]:
    """Grup adindan spec listesine esleme (siralama korunur)."""
    result: dict[str, list[ToolSpec]] = {}
    for spec in TOOLS:
        result.setdefault(spec.group, []).append(spec)
    return result


def enabled_specs(disabled_groups: set[str] | None = None) -> list[ToolSpec]:
    """``MCP_DISABLE_GROUPS`` ile kapatilan gruplar haric tum spec'ler."""
    disabled = disabled_groups or set()
    return [spec for spec in TOOLS if spec.group not in disabled]
