"""CLI entegrasyon testleri.

Kapsam:
- T3.2e akisi: login -> yeni client instance ayni store -> 401 auto-refresh
  -> basari; logout -> AuthError (temiz hata, exit 1).
- ``FileTokenStore`` birim testleri: Fernet sifreleme (duz metin YOK),
  chmod 600, anahtar/bozuk dosya -> AuthError.
- Her grup en az 1 komut (auth, account, market, economy, portfolio,
  analysis, bots, export, misc, config).
- ``fl price history ASELS 1mo 5m`` konumsal period/interval (5m siniri: 60 gun).
- ``fl download`` CSV icerik + varsayilan dosya adi.
- ``--json`` ciktilari ``json.loads`` ile dogrulanir; hatalar stderr'de
  ``{error: {code, status, detail}}`` biciminde.
- ``FlatTyperGroup`` entegrasyonu: ``fl report ASELS`` vs ``fl report get 42``
  ayri calisir; global ``--json`` degeri flat gruba ulasir.

TAMAMEN OFFLINE: tum HTTP istekleri respx ile mocklanir; token store
``FLORENCE_KEYRING=0`` + ``FLORENCE_TOKEN_STORE_PATH`` ile tmp dizine
yonlendirilir. Komutlar ``florence.cli.app._run`` uzerinden gercek komut
agacinda (hata yakalayici + FlatTyperGroup dahil) calistirilir.
"""

from __future__ import annotations

import contextlib
import io
import json
import stat
from pathlib import Path

import httpx
import pytest
import respx

from florence import AuthError
from florence.cli.app import _run
from florence.store import FileTokenStore

API = "https://api.florencex.com.tr"
P = f"{API}/api/v1"

GZIP_BYTES = b"\x1f\x8b\x08\x00mock-gzip-content"


def _login(access: str = "at-1", refresh: str = "rt-1") -> dict:
    return {"access_token": access, "refresh_token": refresh, "token_type": "bearer"}


@pytest.fixture
def cli_env(tmp_path: Path) -> dict[str, str]:
    """CLI'yi tmp dizine yonlendirir (config + Fernet token store)."""
    return {
        "FLORENCE_KEYRING": "0",
        "FLORENCE_TOKEN_STORE_PATH": str(tmp_path / "tokens.json"),
        "XDG_CONFIG_HOME": str(tmp_path / "xdg"),
    }


def run_cli(
    monkeypatch: pytest.MonkeyPatch,
    args: list[str],
    env: dict[str, str] | None = None,
) -> tuple[int, str, str]:
    """CLI'yi gercek komut agacindan calistirir: (exit_code, stdout, stderr)."""
    for key, value in (env or {}).items():
        monkeypatch.setenv(key, value)
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = _run(args, prog_name="fl")
    return code, out.getvalue(), err.getvalue()


# ======================================================================
# FileTokenStore birim testleri (T3.2b)
# ======================================================================
def test_file_store_encrypted_restricted(tmp_path: Path) -> None:
    path = tmp_path / "tokens.json"
    store = FileTokenStore(path, key_material="test-key-1")
    store.set_tokens("at-gizli", "rt-gizli")
    store.set_username("efe")
    store.set_password("bot-1", "s3cret-pw")

    raw = path.read_text(encoding="utf-8")
    # Dosya icerigi duz metin DEGIL: tokenlar/sifreler sifreli blokta.
    assert "at-gizli" not in raw
    assert "rt-gizli" not in raw
    assert "s3cret-pw" not in raw
    assert raw.startswith('{"v": 1, "data": "gAAAA')
    # chmod 600.
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_file_store_wrong_key_raises_auth_error(tmp_path: Path) -> None:
    path = tmp_path / "tokens.json"
    FileTokenStore(path, key_material="key-a").set_tokens("at-1", "rt-1")
    other = FileTokenStore(path, key_material="key-b")
    with pytest.raises(AuthError) as exc:
        other.get_access_token()
    assert exc.value.code == "token_store_corrupt"


def test_file_store_missing_machine_key_raises_auth_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Makine kimligi yoksa GUVENLI hata (sessiz bellek fallback'i YOK)."""
    monkeypatch.delenv("FLORENCE_TOKEN_STORE_PATH", raising=False)
    monkeypatch.setattr("florence.store._machine_id", lambda: None)
    with pytest.raises(AuthError) as exc:
        FileTokenStore(tmp_path / "x.json")
    assert exc.value.code == "no_machine_key"


def test_file_store_bot_password_cleanup(tmp_path: Path) -> None:
    store = FileTokenStore(tmp_path / "t.json", key_material="k")
    store.set_password("bot-1", "pw-1")
    assert store.get_password("bot-1") == "pw-1"
    store.delete_password("bot-1")
    assert store.get_password("bot-1") is None


# ======================================================================
# T3.2e akisi: login -> ayni store'dan yeni client -> 401 refresh -> logout
# ======================================================================
def test_t32e_login_refresh_logout_flow(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cli_env: dict[str, str]
) -> None:
    store_path = tmp_path / "tokens.json"

    # 1) Login (CLI): tokenlar + username Fernet store dosyasina yazilir.
    with respx.mock:
        respx.post(f"{P}/auth/login").mock(return_value=httpx.Response(200, json=_login()))
        code, out, err = run_cli(monkeypatch, ["auth", "login", "efe", "--password", "sifre12345"], env=cli_env)
    assert code == 0
    assert "Giriş yapıldı: efe" in out

    # 2) Yeni client instance — ayni store dosyasi (kalicilik dogrulamasi).
    store = FileTokenStore(store_path)
    assert store.get_username() == "efe"
    assert store.get_access_token() == "at-1"
    assert store.get_refresh_token() == "rt-1"

    # 3) JWT endpoint'inde 401 -> otomatik refresh -> basari (CLI uzerinden).
    with respx.mock:
        respx.get(url__regex=r".*/news/THYAO.*").mock(
            side_effect=[
                httpx.Response(401, json={"detail": "Invalid or expired access token"}),
                httpx.Response(200, json=[{"title": "THYAO haberi"}]),
            ]
        )
        respx.post(f"{P}/auth/refresh").mock(return_value=httpx.Response(200, json=_login("at-2", "rt-2")))
        code, out, err = run_cli(monkeypatch, ["market", "news", "THYAO", "--json"], env=cli_env)
    assert code == 0
    assert json.loads(out)[0]["title"] == "THYAO haberi"
    assert FileTokenStore(store_path).get_access_token() == "at-2"  # refresh rotate

    # 4) Logout -> store temizlenir.
    with respx.mock:
        respx.post(f"{P}/auth/logout").mock(return_value=httpx.Response(200, json={"message": "Logged out"}))
        code, out, err = run_cli(monkeypatch, ["auth", "logout"], env=cli_env)
    assert code == 0
    assert FileTokenStore(store_path).get_access_token() is None

    # 5) Logout sonrasi JWT cagrisi -> refresh token yok -> AuthError, exit 1.
    with respx.mock:
        respx.get(url__regex=r".*/news/THYAO.*").mock(
            return_value=httpx.Response(401, json={"detail": "no token"})
        )
        code, out, err = run_cli(monkeypatch, ["market", "news", "THYAO", "--json"], env=cli_env)
    assert code == 1
    assert out == ""  # stdout'a veri karismaz
    error = json.loads(err)
    assert error["error"]["code"] == "no_refresh_token"
    assert error["error"]["status"] == 401


# ======================================================================
# Grup kapsam testleri (her grup en az 1 komut)
# ======================================================================
def test_group_auth_status_offline(
    monkeypatch: pytest.MonkeyPatch, cli_env: dict[str, str]
) -> None:
    """auth status: yerel (ag yok), login yokken temiz cikti + exit 0."""
    code, out, err = run_cli(monkeypatch, ["auth", "status", "--json"], env=cli_env)
    assert code == 0
    data = json.loads(out)
    assert data["authenticated"] is False
    assert data["store"] == "file"
    assert data["env_override"] is False


def test_group_account_credits(monkeypatch: pytest.MonkeyPatch, cli_env: dict[str, str]) -> None:
    with respx.mock:
        respx.get(f"{P}/credits").mock(return_value=httpx.Response(200, json={"credits": 123.45}))
        code, out, err = run_cli(monkeypatch, ["account", "credits", "--json"], env=cli_env)
    assert code == 0
    assert json.loads(out)["credits"] == 123.45


def test_group_market_price(monkeypatch: pytest.MonkeyPatch, cli_env: dict[str, str]) -> None:
    with respx.mock:
        respx.get(f"{P}/price/current").mock(
            return_value=httpx.Response(200, json={"ticker": "THYAO", "price": 313.4, "market_status": "open"})
        )
        code, out, err = run_cli(monkeypatch, ["market", "price", "THYAO", "--json"], env=cli_env)
    assert code == 0
    data = json.loads(out)
    assert data["ticker"] == "THYAO"
    assert data["price"] == 313.4


def test_group_economy_normalize_tr_decimal(
    monkeypatch: pytest.MonkeyPatch, cli_env: dict[str, str]
) -> None:
    """Backend \"40,25\" -> --json'da float 40.25 (sunum katmani normalizasyonu)."""
    with respx.mock:
        respx.get(f"{P}/economy/silver-price").mock(
            return_value=httpx.Response(200, json={"silver": "40,25"})
        )
        code, out, err = run_cli(monkeypatch, ["economy", "silver", "--json"], env=cli_env)
    assert code == 0
    assert json.loads(out) == {"silver": 40.25}


def test_group_portfolio_list(monkeypatch: pytest.MonkeyPatch, cli_env: dict[str, str]) -> None:
    with respx.mock:
        respx.get(f"{P}/portfolios").mock(return_value=httpx.Response(200, json=[]))
        code, out, err = run_cli(monkeypatch, ["portfolio", "list", "--json"], env=cli_env)
    assert code == 0
    assert json.loads(out) == []


def test_group_analysis_fit(monkeypatch: pytest.MonkeyPatch, cli_env: dict[str, str]) -> None:
    with respx.mock:
        route = respx.post(f"{P}/stocks/fit").mock(
            return_value=httpx.Response(200, json=[{"ticker": "ASELS", "score": 0.9}])
        )
        code, out, err = run_cli(
            monkeypatch, ["analysis", "fit", "--risk-tolerance", "low", "--limit", "3", "--json"], env=cli_env
        )
    assert code == 0
    assert json.loads(out)[0]["ticker"] == "ASELS"
    body = json.loads(route.calls.last.request.content)
    assert body["limit"] == 3
    assert body["risk_tolerance"] == "low"


def test_group_bots_list(monkeypatch: pytest.MonkeyPatch, cli_env: dict[str, str]) -> None:
    with respx.mock:
        respx.get(f"{P}/bots").mock(return_value=httpx.Response(200, json={"bots": []}))
        code, out, err = run_cli(monkeypatch, ["bots", "list", "--json"], env=cli_env)
    assert code == 0
    assert json.loads(out) == {"bots": []}


def test_group_export_list(monkeypatch: pytest.MonkeyPatch, cli_env: dict[str, str]) -> None:
    with respx.mock:
        respx.get(f"{P}/data/export").mock(return_value=httpx.Response(200, json=[]))
        code, out, err = run_cli(monkeypatch, ["export", "list", "--json"], env=cli_env)
    assert code == 0
    assert json.loads(out) == []


def test_group_misc_health(monkeypatch: pytest.MonkeyPatch, cli_env: dict[str, str]) -> None:
    """health kok seviye (prefix'siz) endpoint'e gider."""
    with respx.mock:
        respx.get(f"{API}/health").mock(return_value=httpx.Response(200, json={"status": "ok"}))
        code, out, err = run_cli(monkeypatch, ["misc", "health", "--json"], env=cli_env)
    assert code == 0
    assert json.loads(out) == {"status": "ok"}


def test_group_config_show(monkeypatch: pytest.MonkeyPatch, cli_env: dict[str, str]) -> None:
    code, out, err = run_cli(monkeypatch, ["config", "show", "--json"], env=cli_env)
    assert code == 0
    data = json.loads(out)
    assert data["api_url"]["source"] in ("env", "config", "default")
    assert data["default_output"]["value"] == "table"
    assert data["store"] == "file"


# ======================================================================
# bots create / delete (sifre maskesi + store temizligi)
# ======================================================================
def test_bots_create_masks_password_and_stores_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cli_env: dict[str, str]
) -> None:
    store_path = tmp_path / "tokens.json"
    with respx.mock:
        respx.post(f"{P}/bots").mock(
            return_value=httpx.Response(
                200, json={"id": 5, "username": "bot-1", "email": "bot-1@x", "password": "tek-seferlik"}
            )
        )
        code, out, err = run_cli(monkeypatch, ["bots", "create", "bot-1", "--json"], env=cli_env)
    assert code == 0
    data = json.loads(out)
    assert data["password"] == "***"  # varsayilan: maskeli
    assert data["id"] == 5
    # Tek seferlik sifre store'a yazildi (ekrana basilmadi).
    assert FileTokenStore(store_path).get_password("bot-1") == "tek-seferlik"
    assert "tek-seferlik" not in out


def test_bots_create_show_password(monkeypatch: pytest.MonkeyPatch, cli_env: dict[str, str]) -> None:
    with respx.mock:
        respx.post(f"{P}/bots").mock(
            return_value=httpx.Response(200, json={"id": 6, "username": "bot-2", "password": "goster"})
        )
        code, out, err = run_cli(
            monkeypatch, ["bots", "create", "bot-2", "--show-password", "--json"], env=cli_env
        )
    assert code == 0
    assert json.loads(out)["password"] == "goster"


def test_bots_delete_cleans_stored_password(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cli_env: dict[str, str]
) -> None:
    store_path = tmp_path / "tokens.json"
    # CLI ile AYNI anahtar turetimi (makine kimligi) — key_material verilmez.
    FileTokenStore(store_path).set_password("bot-1", "pw-gizli")
    with respx.mock:
        respx.get(f"{P}/bots").mock(
            return_value=httpx.Response(200, json={"bots": [{"id": 5, "username": "bot-1"}]})
        )
        respx.delete(f"{P}/bots/5").mock(return_value=httpx.Response(200, json={"message": "Bot deleted"}))
        code, out, err = run_cli(monkeypatch, ["bots", "delete", "5", "--yes", "--json"], env=cli_env)
    assert code == 0
    assert FileTokenStore(store_path).get_password("bot-1") is None


def test_bots_delete_requires_yes_in_json_mode(
    monkeypatch: pytest.MonkeyPatch, cli_env: dict[str, str]
) -> None:
    """--json + onay promptu -> exit 2 (interaktif surpriz yok)."""
    code, out, err = run_cli(monkeypatch, ["bots", "delete", "5", "--json"], env=cli_env)
    assert code == 2
    error = json.loads(err)
    assert error["error"]["code"] == "prompt_required"


# ======================================================================
# export create / download / fetch
# ======================================================================
def _export_record(export_id: int, status: str, token: str | None = None) -> dict:
    return {
        "id": export_id,
        "year": 2025,
        "format": "csv",
        "status": status,
        "created_at": "2026-08-01T10:00:00+00:00",
        "row_count": 250,
        "size_bytes": 1234,
        "downloadable": status in ("ready", "sent"),
        "download_url": f"/api/v1/data/export/download/{token}" if token else None,
        "error": None,
    }


def test_export_create(monkeypatch: pytest.MonkeyPatch, cli_env: dict[str, str]) -> None:
    with respx.mock:
        route = respx.post(f"{P}/data/export").mock(
            return_value=httpx.Response(202, json={"export_id": 9, "status": "queued"})
        )
        code, out, err = run_cli(monkeypatch, ["export", "create", "2025", "--json"], env=cli_env)
    assert code == 0
    assert json.loads(out) == {"export_id": 9, "status": "queued"}
    body = json.loads(route.calls.last.request.content)
    assert body == {"year": 2025, "format": "csv"}


def test_export_create_invalid_format_exit_2(
    monkeypatch: pytest.MonkeyPatch, cli_env: dict[str, str]
) -> None:
    code, out, err = run_cli(monkeypatch, ["export", "create", "2025", "--format", "xlsx"], env=cli_env)
    assert code == 2


def test_export_download_waits_and_writes_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cli_env: dict[str, str]
) -> None:
    state = {"polls": 0}

    def status_handler(request: httpx.Request) -> httpx.Response:
        state["polls"] += 1
        if state["polls"] < 2:
            return httpx.Response(200, json=_export_record(9, "processing"))
        return httpx.Response(200, json=_export_record(9, "ready", token="tok-9"))

    dest = tmp_path / "veri.csv.gz"
    with respx.mock:
        respx.get(f"{P}/data/export/9").mock(side_effect=status_handler)
        respx.get(f"{P}/data/export/download/tok-9").mock(
            return_value=httpx.Response(200, content=GZIP_BYTES)
        )
        code, out, err = run_cli(
            monkeypatch,
            ["export", "download", "9", "--output", str(dest), "--poll-interval", "0", "--json"],
            env=cli_env,
        )
    assert code == 0
    data = json.loads(out)
    assert data["export_id"] == 9
    assert data["status"] == "ready"
    assert Path(data["path"]).read_bytes() == GZIP_BYTES
    assert state["polls"] == 2
    assert "Bekleniyor" in err  # progress stderr'de kaldi


def test_export_download_nowait_not_ready(
    monkeypatch: pytest.MonkeyPatch, cli_env: dict[str, str]
) -> None:
    with respx.mock:
        respx.get(f"{P}/data/export/9").mock(
            return_value=httpx.Response(200, json=_export_record(9, "processing"))
        )
        code, out, err = run_cli(
            monkeypatch, ["export", "download", "9", "--no-wait", "--json"], env=cli_env
        )
    assert code == 0
    data = json.loads(out)
    assert data["status"] == "processing"
    assert data["path"] is None


def test_export_fetch_composite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cli_env: dict[str, str]
) -> None:
    """fetch = create -> wait -> download (tek komut)."""

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/data/export") and request.method == "POST":
            return httpx.Response(202, json={"export_id": 7, "status": "queued"})
        if path.endswith("/data/export/7"):
            return httpx.Response(200, json=_export_record(7, "sent", token="tok-7"))
        if path.endswith("/data/export/download/tok-7"):
            return httpx.Response(200, content=GZIP_BYTES)
        return httpx.Response(404, json={"detail": "unmocked"})

    dest = tmp_path / "yillik.csv.gz"
    with respx.mock:
        respx.post(f"{P}/data/export").mock(side_effect=handler)
        respx.get(f"{P}/data/export/7").mock(side_effect=handler)
        respx.get(f"{P}/data/export/download/tok-7").mock(side_effect=handler)
        code, out, err = run_cli(
            monkeypatch,
            ["export", "fetch", "2025", "--format", "csv", "--output", str(dest), "--poll-interval", "0", "--json"],
            env=cli_env,
        )
    assert code == 0
    data = json.loads(out)
    assert data["export_id"] == 7
    assert data["status"] == "sent"
    assert Path(data["path"]).read_bytes() == GZIP_BYTES


# ======================================================================
# fl price (flat grup) — konumsal period/interval + kisa yol
# ======================================================================
def test_flat_price_history_positional_period_interval(
    monkeypatch: pytest.MonkeyPatch, cli_env: dict[str, str]
) -> None:
    """fl price history ASELS 1mo 5m -> period=1mo&interval=5m (konumsal)."""
    with respx.mock:
        route = respx.get(url__regex=r".*/price/history/ASELS.*").mock(
            return_value=httpx.Response(200, json=[{"ts": "2026-08-01", "close": 42.5}])
        )
        code, out, err = run_cli(
            monkeypatch, ["price", "history", "ASELS", "1mo", "5m", "--json"], env=cli_env
        )
    assert code == 0
    assert json.loads(out)[0]["close"] == 42.5
    request = route.calls.last.request
    assert request.url.params["period"] == "1mo"
    assert request.url.params["interval"] == "5m"


def test_flat_price_history_normalizes_1m_to_1mo(
    monkeypatch: pytest.MonkeyPatch, cli_env: dict[str, str]
) -> None:
    """fl price history THYAO 1m 5m -> period normalizes 1m->1mo (sinir ici)."""
    with respx.mock:
        route = respx.get(url__regex=r".*/price/history/THYAO.*").mock(
            return_value=httpx.Response(200, json=[])
        )
        code, out, err = run_cli(
            monkeypatch, ["price", "history", "THYAO", "1m", "5m", "--json"], env=cli_env
        )
    assert code == 0
    assert route.calls.last.request.url.params["period"] == "1mo"


def test_flat_price_history_rejects_over_limit_period(
    monkeypatch: pytest.MonkeyPatch, cli_env: dict[str, str]
) -> None:
    """3mo (90 gun) + 5m (limit 60 gun) -> net hata; backend'e istek gitmez."""
    code, out, err = run_cli(
        monkeypatch, ["price", "history", "THYAO", "3mo", "5m", "--json"], env=cli_env
    )
    assert code == 2
    assert "60 gün" in err
    assert "3mo" in err


def test_flat_price_shortcut_current(monkeypatch: pytest.MonkeyPatch, cli_env: dict[str, str]) -> None:
    """fl price THYAO -> guncel fiyat (flat grup, alt komut yok)."""
    with respx.mock:
        respx.get(f"{P}/price/current").mock(
            return_value=httpx.Response(200, json={"ticker": "THYAO", "price": 313.4})
        )
        code, out, err = run_cli(monkeypatch, ["price", "THYAO", "--json"], env=cli_env)
    assert code == 0
    assert json.loads(out)["price"] == 313.4


# ======================================================================
# fl download — hisse mum CSV'si
# ======================================================================
def test_download_csv_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cli_env: dict[str, str]
) -> None:
    history = [
        {"ts": "2026-08-01T00:00:00+00:00", "open": 40.1, "close": 41.2, "volume": 1000},
        {"ts": "2026-08-02T00:00:00+00:00", "open": 41.2, "close": 42.5, "volume": 2000},
    ]
    dest = tmp_path / "thyao.csv"
    with respx.mock:
        respx.get(url__regex=r".*/price/history/THYAO.*").mock(
            return_value=httpx.Response(200, json=history)
        )
        code, out, err = run_cli(
            monkeypatch, ["download", "THYAO", "3m", "--output", str(dest), "--json"], env=cli_env
        )
    assert code == 0
    data = json.loads(out)
    assert data["ticker"] == "THYAO"
    assert data["period"] == "3mo"
    assert data["rows"] == 2
    content = Path(data["path"]).read_text(encoding="utf-8")
    assert content.splitlines()[0] == "ts,open,close,volume"
    assert "2026-08-02" in content


def test_download_default_filename(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cli_env: dict[str, str]
) -> None:
    monkeypatch.chdir(tmp_path)
    with respx.mock:
        respx.get(url__regex=r".*/price/history/THYAO.*").mock(
            return_value=httpx.Response(200, json=[{"ts": "2026-08-01", "close": 1.0}])
        )
        code, out, err = run_cli(monkeypatch, ["download", "THYAO", "3m"], env=cli_env)
    assert code == 0
    assert (tmp_path / "THYAO-3mo.csv").exists()
    assert "CSV yazıldı" in out


# ======================================================================
# FlatTyperGroup entegrasyonu (bilinen risk: typer 0.27 + flat grup)
# ======================================================================
def test_flat_report_positional_ticker_vs_subcommand(
    monkeypatch: pytest.MonkeyPatch, cli_env: dict[str, str]
) -> None:
    """fl report ASELS (generate) ile fl report get 42 (alt komut) ayri calisir."""
    with respx.mock:
        gen = respx.post(f"{P}/reports/generate").mock(
            return_value=httpx.Response(200, json={"report_id": 1, "success": True, "credits_spend": 0.5})
        )
        code, out, err = run_cli(monkeypatch, ["report", "ASELS", "--json"], env=cli_env)
    assert code == 0
    assert json.loads(out)["report_id"] == 1
    request = gen.calls.last.request
    assert request.url.params["ticker"] == "ASELS"
    assert request.url.params["type"] == "quick_report"

    with respx.mock:
        get_route = respx.get(f"{P}/reports/42").mock(
            return_value=httpx.Response(200, json={"id": 42, "report": "# Rapor"})
        )
        code, out, err = run_cli(monkeypatch, ["report", "get", "42", "--json"], env=cli_env)
    assert code == 0
    assert json.loads(out)["id"] == 42
    assert get_route.called


def test_flat_report_deep_flag(monkeypatch: pytest.MonkeyPatch, cli_env: dict[str, str]) -> None:
    with respx.mock:
        gen = respx.post(f"{P}/reports/generate").mock(
            return_value=httpx.Response(200, json={"report_id": 2, "success": True})
        )
        code, out, err = run_cli(monkeypatch, ["report", "ASELS", "--deep", "--json"], env=cli_env)
    assert code == 0
    assert gen.calls.last.request.url.params["type"] == "deep_report"


def test_flat_global_json_reaches_command(
    monkeypatch: pytest.MonkeyPatch, cli_env: dict[str, str]
) -> None:
    """Global --json (komuttan once) flat gruba ulasir: fl --json report ASELS."""
    with respx.mock:
        respx.post(f"{P}/reports/generate").mock(
            return_value=httpx.Response(200, json={"report_id": 7, "success": True})
        )
        code, out, err = run_cli(monkeypatch, ["--json", "report", "ASELS"], env=cli_env)
    assert code == 0
    assert json.loads(out)["report_id"] == 7


def test_flat_simulate_run_and_cost(monkeypatch: pytest.MonkeyPatch, cli_env: dict[str, str]) -> None:
    """fl simulate THYAO --days 30 (run) vs fl simulate cost (alt komut)."""
    with respx.mock:
        run_route = respx.get(url__regex=r".*/simulations/THYAO.*").mock(
            return_value=httpx.Response(200, json={"simulation_id": 1, "prob_above": 0.6})
        )
        code, out, err = run_cli(
            monkeypatch, ["simulate", "THYAO", "--days", "30", "--json"], env=cli_env
        )
    assert code == 0
    assert json.loads(out)["prob_above"] == 0.6
    assert run_route.calls.last.request.url.params["days"] == "30"

    with respx.mock:
        respx.get(f"{P}/simulations/per-day-cost").mock(
            return_value=httpx.Response(200, json={"cost": 1.5})
        )
        code, out, err = run_cli(monkeypatch, ["simulate", "cost", "--json"], env=cli_env)
    assert code == 0
    assert json.loads(out)["cost"] == 1.5


# ======================================================================
# Hata bicimleri ve kullanim hatalari
# ======================================================================
def test_json_error_format_on_stderr(monkeypatch: pytest.MonkeyPatch, cli_env: dict[str, str]) -> None:
    with respx.mock:
        respx.get(f"{P}/price/current").mock(
            return_value=httpx.Response(404, json={"detail": "error_not_found"})
        )
        code, out, err = run_cli(monkeypatch, ["market", "price", "THYAO", "--json"], env=cli_env)
    assert code == 1
    assert out == ""  # stdout = veri; hata stderr'de
    error = json.loads(err)
    assert error["error"]["code"] == "error_not_found"
    assert error["error"]["status"] == 404
    assert isinstance(error["error"]["detail"], str)


def test_unknown_command_exit_2(monkeypatch: pytest.MonkeyPatch, cli_env: dict[str, str]) -> None:
    code, out, err = run_cli(monkeypatch, ["market", "yok-boyle-komut"], env=cli_env)
    assert code == 2


def test_config_set_allowlist_rejects(monkeypatch: pytest.MonkeyPatch, cli_env: dict[str, str]) -> None:
    """Allowlist disi anahtar -> exit 2 (last_username yalnizca CLI yazar)."""
    code, out, err = run_cli(monkeypatch, ["config", "set", "last_username", "efe"], env=cli_env)
    assert code == 2
    assert "Geçersiz config anahtarı" in err


def test_config_set_tui_default_chart(
    monkeypatch: pytest.MonkeyPatch, cli_env: dict[str, str], tmp_path: Path
) -> None:
    """``tui_default_chart`` allowlist'te (line|candle); gecersiz deger exit 2 (P6)."""
    code, out, err = run_cli(monkeypatch, ["config", "set", "tui_default_chart", "candle"], env=cli_env)
    assert code == 0
    cfg_file = tmp_path / "xdg" / "florence" / "config.toml"
    assert 'tui_default_chart = "candle"' in cfg_file.read_text(encoding="utf-8")

    code, out, err = run_cli(monkeypatch, ["config", "set", "tui_default_chart", "pasta"], env=cli_env)
    assert code == 2
    assert "tui_default_chart" in err
    # Dosya degismedi (gecersiz deger yazilmadi).
    assert 'tui_default_chart = "candle"' in cfg_file.read_text(encoding="utf-8")


def test_config_set_and_show_roundtrip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cli_env: dict[str, str]
) -> None:
    code, out, err = run_cli(monkeypatch, ["config", "set", "default_output", "json"], env=cli_env)
    assert code == 0
    cfg_file = tmp_path / "xdg" / "florence" / "config.toml"
    assert 'default_output = "json"' in cfg_file.read_text(encoding="utf-8")

    code, out, err = run_cli(monkeypatch, ["config", "show", "--json"], env=cli_env)
    assert code == 0
    data = json.loads(out)
    assert data["default_output"] == {"value": "json", "source": "config"}


def test_misc_ipo_and_legal_text(
    monkeypatch: pytest.MonkeyPatch, cli_env: dict[str, str]
) -> None:
    """misc alt varliklari (ipo) + legal metin ciktisi."""
    with respx.mock:
        respx.get(f"{P}/ipos/upcoming").mock(
            return_value=httpx.Response(200, json=[{"slug": "x", "name": "X A.S."}])
        )
        code, out, err = run_cli(monkeypatch, ["misc", "ipo", "upcoming", "--json"], env=cli_env)
    assert code == 0
    assert json.loads(out)[0]["slug"] == "x"

    with respx.mock:
        respx.get(f"{P}/legal").mock(
            return_value=httpx.Response(200, json={"policy": "terms", "content": "Metin icerigi"})
        )
        code, out, err = run_cli(monkeypatch, ["misc", "legal", "terms"], env=cli_env)
    assert code == 0
    assert "Metin icerigi" in out


def test_export_timeout_exit_1(monkeypatch: pytest.MonkeyPatch, cli_env: dict[str, str]) -> None:
    """Poll timeout -> CliRuntimeError (code=timeout), exit 1."""
    with respx.mock:
        respx.get(f"{P}/data/export/9").mock(
            return_value=httpx.Response(200, json=_export_record(9, "processing"))
        )
        code, out, err = run_cli(
            monkeypatch,
            ["export", "download", "9", "--wait", "--timeout", "0", "--poll-interval", "0", "--json"],
            env=cli_env,
        )
    assert code == 1
    error = json.loads(err.splitlines()[-1])  # progress stderr'de; son satir JSON hata
    assert error["error"]["code"] == "timeout"
