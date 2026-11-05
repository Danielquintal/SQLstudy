"""Login da página do paciente: data de nascimento + código de 6 números.

A página publicada não leva os dados abertos: o HTML inteiro vai criptografado (AES-256-GCM, chave tirada com
PBKDF2-SHA256 de "ddmmaaaa:código", 600 mil rodadas) dentro de uma página pequena com a tela de login. Com a data e o
código certos, o navegador do paciente descriptografa e abre a página normal; sem eles, só existe texto ilegível.
A aba "Evolução" da ficha, no sistema, continua mostrando a página aberta (não passa por aqui).

Segurança: é uma proteção real do conteúdo, mas a senha tem só 6 números além da data de nascimento; não é nível
bancário. Para trocar o acesso de um paciente, gere outro código na ficha e atualize o link.
"""
import base64
import hashlib
import html as html_mod
import json
import os
import secrets

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

RODADAS = 600_000


def codigo(cur, pid, novo=False):
    """código de acesso do paciente (cria na primeira vez, ou um novo quando pedido)"""
    cur.execute("SELECT codigo_acesso FROM paciente WHERE id = %s", (pid,))
    r = cur.fetchone()
    if r and r[0] and not novo:
        return r[0]
    c = f"{secrets.randbelow(10 ** 6):06d}"
    cur.execute("UPDATE paciente SET codigo_acesso = %s WHERE id = %s", (c, pid))
    return c


def credenciais(cur, pid):
    """{"nasc": "ddmmaaaa" ou "", "codigo": "123456"} para proteger a página"""
    cur.execute("SELECT data_nascimento FROM paciente WHERE id = %s", (pid,))
    r = cur.fetchone()
    nasc = r[0].strftime("%d%m%Y") if r and r[0] else ""
    cod = codigo(cur, pid)
    # sal fixo enquanto o código e a data não mudam: a chave guardada no aparelho do paciente ("lembrar") continua
    # valendo quando o link é atualizado; trocar o código derruba os aparelhos lembrados
    sal = hashlib.sha256(f"res-athleticae:{pid}:{nasc}:{cod}".encode()).hexdigest()[:32]
    return {"nasc": nasc, "codigo": cod, "sal": sal}


def _b64(b):
    return base64.b64encode(b).decode()


def proteger(pagina_html, nome, nasc, cod, whatsapp="", sal=None):
    """HTML da página aberta -> página com login e o conteúdo criptografado (iv novo a cada vez; sal fixo por paciente)"""
    sal, iv = (bytes.fromhex(sal) if sal else os.urandom(16)), os.urandom(12)
    chave = hashlib.pbkdf2_hmac("sha256", f"{nasc}:{cod}".encode(), sal, RODADAS, 32)
    cifra = AESGCM(chave).encrypt(iv, pagina_html.encode("utf-8"), None)   # texto cifrado + etiqueta, como o WebCrypto
    dados = {"s": _b64(sal), "i": _b64(iv), "c": _b64(cifra), "n": RODADAS, "d": bool(nasc)}
    primeiro = nome.strip().split()[0].title() if nome.strip() else ""
    zap = (f"https://wa.me/{whatsapp}?text=" + _url(f"Olá! Aqui é {nome.strip()}. Não estou conseguindo entrar na minha "
                                                     f"página de acompanhamento: pode me mandar o código de acesso?")) if whatsapp else ""
    return (LOGIN.replace("__TITULO__", html_mod.escape(nome.strip()))
            .replace("__PRIMEIRO__", html_mod.escape(primeiro))
            .replace("__ZAP__", json.dumps(zap))
            .replace("__CIFRA__", json.dumps(dados)))


def _url(t):
    from urllib.parse import quote
    return quote(t)


LOGIN = r"""<title>__TITULO__</title>
<style>
:root{--bg:#F2F6F6;--surface:#FFFFFF;--ink:#13262E;--muted:#5E7178;--line:#DCE5E6;--brand:#12434F;--brand-ink:#FFFFFF;
  --brand-soft:#C9DCDF;--c2:#1A9E8F;--bad:#C2452D;--sans:"IBM Plex Sans",system-ui,-apple-system,"Segoe UI",sans-serif}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--bg:#0E1A1D;--surface:#15252A;--ink:#E4EEEF;--muted:#93A8AD;
  --line:#26393E;--brand:#0B2C34;--brand-ink:#E4EEEF;--brand-soft:#8FB3B9;--c2:#3CC4B2;--bad:#FF7A5C;color-scheme:dark}}
:root[data-theme="dark"]{--bg:#0E1A1D;--surface:#15252A;--ink:#E4EEEF;--muted:#93A8AD;--line:#26393E;--brand:#0B2C34;
  --brand-ink:#E4EEEF;--brand-soft:#8FB3B9;--c2:#3CC4B2;--bad:#FF7A5C;color-scheme:dark}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.5 var(--sans);min-height:100vh;display:flex;flex-direction:column}
.faixa{background:var(--brand);color:var(--brand-ink);padding:28px max(16px,env(safe-area-inset-left,0px)) 64px}
.faixa p{margin:0 auto;max-width:440px;font-size:12px;letter-spacing:.12em;text-transform:uppercase;color:var(--brand-soft)}
.cartao{background:var(--surface);border:1px solid var(--line);border-radius:16px;max-width:440px;width:calc(100% - 32px);
  margin:-40px auto 32px;padding:24px 22px;display:flex;flex-direction:column;gap:14px}
h1{margin:0;font-size:22px;font-weight:600;text-wrap:balance}
.sub{margin:0;color:var(--muted);font-size:15px}
label{display:flex;flex-direction:column;gap:6px;font-size:14px;font-weight:500}
input[type=text]{font:500 20px var(--sans);letter-spacing:.06em;padding:12px 14px;border-radius:10px;border:1px solid var(--line);
  background:var(--bg);color:var(--ink);width:100%}
input[type=text]:focus{outline:2px solid var(--c2);outline-offset:1px}
.lembrar{flex-direction:row;align-items:center;gap:8px;font-weight:400;color:var(--muted)}
.lembrar input{width:18px;height:18px;accent-color:var(--c2)}
button{appearance:none;border:0;background:var(--c2);color:#fff;font:600 17px var(--sans);padding:14px;border-radius:10px;cursor:pointer}
button:disabled{opacity:.6;cursor:progress}
button:focus-visible{outline:2px solid var(--ink);outline-offset:2px}
.msg{margin:0;font-size:14px;min-height:1.4em}
.msg.erro{color:var(--bad)}
.ajuda{margin:0;font-size:14px;color:var(--muted)}
.ajuda a{color:var(--c2);font-weight:600}
</style>
<div class="faixa"><p>Res Athleticae</p></div>
<main class="cartao">
  <h1>Olá, __PRIMEIRO__!</h1>
  <p class="sub">Esta é a sua página de acompanhamento. Para abrir, digite sua data de nascimento e o código de acesso
    que seu nutricionista enviou.</p>
  <form id="f" autocomplete="off">
    <div style="display:flex;flex-direction:column;gap:14px">
      <label id="l-nasc">Data de nascimento
        <input type="text" id="nasc" inputmode="numeric" placeholder="dd/mm/aaaa" maxlength="10" autocomplete="bday"></label>
      <label>Código de acesso
        <input type="text" id="cod" inputmode="numeric" placeholder="6 números" maxlength="6" autocomplete="one-time-code"></label>
      <label class="lembrar"><input type="checkbox" id="lembrar" checked> Lembrar neste aparelho</label>
      <button id="entrar">Entrar</button>
      <p class="msg" id="msg" role="status" aria-live="polite"></p>
    </div>
  </form>
  <p class="ajuda" id="ajuda" hidden>Esqueceu o código? <a id="zap" href="#" target="_blank" rel="noopener">Peça pelo WhatsApp</a>.</p>
</main>
<script>
const CIFRA = __CIFRA__;
const ZAP = __ZAP__;
const $ = id => document.getElementById(id);
const bin = b64 => Uint8Array.from(atob(b64), c => c.charCodeAt(0));
const GUARDA = 'acesso-' + CIFRA.s;
if (!CIFRA.d) $('l-nasc').hidden = true;                  // paciente sem data de nascimento: só o código
if (ZAP) { $('zap').href = ZAP; $('ajuda').hidden = false; }
// data com as barras enquanto digita
$('nasc').addEventListener('input', e => {
  const d = e.target.value.replace(/\D/g, '').slice(0, 8);
  e.target.value = d.length > 4 ? `${d.slice(0, 2)}/${d.slice(2, 4)}/${d.slice(4)}` : d.length > 2 ? `${d.slice(0, 2)}/${d.slice(2)}` : d;
});
$('cod').addEventListener('input', e => { e.target.value = e.target.value.replace(/\D/g, '').slice(0, 6); });
async function chave(senha) {
  const base = await crypto.subtle.importKey('raw', new TextEncoder().encode(senha), 'PBKDF2', false, ['deriveKey']);
  return crypto.subtle.deriveKey({ name: 'PBKDF2', salt: bin(CIFRA.s), iterations: CIFRA.n, hash: 'SHA-256' },
    base, { name: 'AES-GCM', length: 256 }, true, ['decrypt']);
}
async function abrir(k) {
  const claro = await crypto.subtle.decrypt({ name: 'AES-GCM', iv: bin(CIFRA.i) }, k, bin(CIFRA.c));
  const html = new TextDecoder().decode(claro);
  document.open(); document.write(html); document.close();
}
async function lembrada() {
  try {
    const raw = localStorage.getItem(GUARDA);
    if (!raw) return false;
    const k = await crypto.subtle.importKey('raw', bin(raw), { name: 'AES-GCM' }, true, ['decrypt']);
    await abrir(k); return true;
  } catch (e) { try { localStorage.removeItem(GUARDA); } catch (e2) {} return false; }
}
$('f').addEventListener('submit', async e => {
  e.preventDefault();
  const nasc = $('nasc').value.replace(/\D/g, ''), cod = $('cod').value.replace(/\D/g, '');
  if (CIFRA.d && nasc.length !== 8) { $('msg').className = 'msg erro'; $('msg').textContent = 'Digite a data de nascimento completa (dd/mm/aaaa).'; return; }
  if (cod.length !== 6) { $('msg').className = 'msg erro'; $('msg').textContent = 'O código tem 6 números.'; return; }
  $('entrar').disabled = true; $('msg').className = 'msg'; $('msg').textContent = 'Abrindo…';
  try {
    const k = await chave(`${CIFRA.d ? nasc : ''}:${cod}`);
    let claro;
    try { claro = await crypto.subtle.decrypt({ name: 'AES-GCM', iv: bin(CIFRA.i) }, k, bin(CIFRA.c)); }
    catch (err) { throw new Error('senha'); }
    if ($('lembrar').checked) {
      try { localStorage.setItem(GUARDA, btoa(String.fromCharCode(...new Uint8Array(await crypto.subtle.exportKey('raw', k))))); } catch (err) {}
    }
    document.open(); document.write(new TextDecoder().decode(claro)); document.close();
  } catch (err) {
    $('entrar').disabled = false; $('msg').className = 'msg erro';
    $('msg').textContent = err.message === 'senha' ? 'Data de nascimento ou código não conferem. Confira e tente de novo.'
      : 'Não foi possível abrir a página neste navegador.';
  }
});
// abre sozinho se a chave foi guardada neste aparelho (só depois de a tela terminar de carregar: antes disso o
// document.open seria ignorado e a página entraria por baixo da tela de login)
if (document.readyState === 'complete') lembrada(); else addEventListener('load', () => lembrada());
</script>
"""
