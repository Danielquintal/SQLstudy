// Medidas por foto (EXPERIMENTAL): circunferências estimadas a partir de uma foto de frente e uma de perfil,
// e % de gordura pela equação da Marinha americana (Hodgdon & Beckett). Não é o método validado com DXA do artigo
// (Ferreira et al., npj Digital Medicine 2025, aplicativo comercial treinado com DXA): aqui são medidas geométricas
// do contorno do corpo, que precisam ser conferidas com a fita.
//
// A detecção do corpo usa o MediaPipe Pose Landmarker (Google, código aberto), que roda NO NAVEGADOR: as fotos não
// saem deste computador e não são guardadas. Só o modelo é baixado da internet (uma vez; depois fica em cache).
//
// As funções de geometria (medir, perimetroElipse, marinha) não dependem do MediaPipe e podem ser testadas sozinhas.

const MP_VERSAO = '0.10.14';
const MP_URL = `https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@${MP_VERSAO}`;
const MODELO = 'https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_full/float16/latest/pose_landmarker_full.task';

// ---------- geometria (máscara do corpo + pontos do esqueleto -> larguras em pixels) ----------

// trecho contínuo de pixels do corpo na linha y que contém a coluna x (ou o mais próximo dela, até `folga` px)
export function trecho(mask, w, y, x, folga = 6) {
  y = Math.round(y);
  const linha = y * w, em = c => c >= 0 && c < w && mask[linha + c];
  let c = Math.round(x);
  if (!em(c)) {
    let achou = -1;
    for (let d = 1; d <= folga && achou < 0; d++) { if (em(c - d)) achou = c - d; else if (em(c + d)) achou = c + d; }
    if (achou < 0) return null;
    c = achou;
  }
  let a = c, b = c;
  while (em(a - 1)) a--;
  while (em(b + 1)) b++;
  return { a, b, larg: b - a + 1, y };
}

// topo (alto da cabeça) e base (pés) do corpo, na faixa central da foto
export function extremos(mask, w, h, xc) {
  const col0 = Math.max(0, Math.round(xc - w * 0.25)), col1 = Math.min(w - 1, Math.round(xc + w * 0.25));
  const tem = y => { for (let x = col0; x <= col1; x++) if (mask[y * w + x]) return true; return false; };
  let topo = 0, base = h - 1;
  while (topo < h && !tem(topo)) topo++;
  while (base > topo && !tem(base)) base--;
  return { topo, base, alt: base - topo + 1 };
}

// a linha mais estreita (ou mais larga) de uma faixa, seguindo o centro do corpo
function busca(mask, w, y0, y1, xc, maior) {
  let melhor = null;
  for (let y = Math.round(Math.min(y0, y1)); y <= Math.round(Math.max(y0, y1)); y++) {
    const t = trecho(mask, w, y, typeof xc === 'function' ? xc(y) : xc);
    if (!t || t.larg < 3) continue;
    if (!melhor || (maior ? t.larg > melhor.larg : t.larg < melhor.larg)) melhor = t;
  }
  return melhor;
}

const media = (a, b) => (a + b) / 2;

// pontos do MediaPipe Pose (índices): 0 nariz, 7/8 orelhas, 11/12 ombros, 23/24 quadris
// pts: [{x, y}] já em pixels. Devolve os níveis e as larguras de frente.
export function medirFrente(mask, w, h, pts) {
  const orelha = media(pts[7].y, pts[8].y), ombro = media(pts[11].y, pts[12].y), quadril = media(pts[23].y, pts[24].y);
  const xc = media(pts[23].x, pts[24].x), xPesc = pts[0].x;
  const T = quadril - ombro;
  const ext = extremos(mask, w, h, xc);
  const niveis = {
    pescoco: busca(mask, w, orelha + 0.35 * (ombro - orelha), ombro - 0.12 * (ombro - orelha), xPesc, false),
    cintura: busca(mask, w, ombro + 0.40 * T, quadril - 0.08 * T, xc, false),       // a mais estreita do tronco
    abdomen: trecho(mask, w, ombro + 0.78 * T, xc),                                   // altura aproximada do umbigo
    quadril: busca(mask, w, quadril - 0.05 * T, quadril + 0.22 * T, xc, true),       // a mais larga do quadril
  };
  return { ext, niveis, T, ombro, quadril };
}

// perfil: mede a profundidade nos mesmos níveis, achados pela posição relativa à altura do corpo
export function medirPerfil(mask, w, h, pts, frente, extFrente) {
  const idx = (a, b) => (pts[a].visibility ?? 1) >= (pts[b].visibility ?? 1) ? a : b;   // lado mais visível
  const ombro = pts[idx(11, 12)], quadril = pts[idx(23, 24)], orelha = pts[idx(7, 8)];
  const xTronco = y => {   // o tronco no perfil: entre o ombro e o quadril
    const t = Math.min(1, Math.max(0, (y - ombro.y) / Math.max(1, quadril.y - ombro.y)));
    return ombro.x + (quadril.x - ombro.x) * t;
  };
  const ext = extremos(mask, w, h, quadril.x);
  // posição relativa (0 = topo da cabeça, 1 = pés) de cada nível na foto de frente
  const rel = y => (y - extFrente.topo) / extFrente.alt;
  const yPerfil = r => ext.topo + r * ext.alt;
  const faixa = (t, maior, janela = 0.015) => t && busca(mask, w, yPerfil(rel(t.y) - janela), yPerfil(rel(t.y) + janela), xTronco, maior);
  const xPesc = media(orelha.x, ombro.x);
  const niveis = {
    pescoco: frente.niveis.pescoco && busca(mask, w, yPerfil(rel(frente.niveis.pescoco.y) - 0.01), yPerfil(rel(frente.niveis.pescoco.y) + 0.01), xPesc, false),
    cintura: faixa(frente.niveis.cintura, false),
    abdomen: faixa(frente.niveis.abdomen, true, 0.01),
    quadril: faixa(frente.niveis.quadril, true),
  };
  return { ext, niveis };
}

// perímetro da elipse (Ramanujan) com largura e profundidade em cm
export function perimetroElipse(larg, prof) {
  const a = larg / 2, b = prof / 2;
  return Math.PI * (3 * (a + b) - Math.sqrt((3 * a + b) * (a + 3 * b)));
}

// % de gordura da Marinha americana (Hodgdon & Beckett, 1984), medidas em cm.
// Homens: abdômen (umbigo) e pescoço; mulheres: cintura (a mais estreita), quadril e pescoço.
export function marinha(sexo, alturaCm, c) {
  const pol = v => v / 2.54, log = Math.log10;
  if (sexo === 'M') {
    if (!(c.abdomen > c.pescoco)) return null;
    return 86.010 * log(pol(c.abdomen - c.pescoco)) - 70.041 * log(pol(alturaCm)) + 36.76;
  }
  if (!(c.cintura + c.quadril > c.pescoco)) return null;
  return 163.205 * log(pol(c.cintura + c.quadril - c.pescoco)) - 97.684 * log(pol(alturaCm)) - 78.387;
}

// junta frente + perfil -> circunferências (cm) e % de gordura
export function calcular(sexo, alturaCm, frente, perfil) {
  const escF = alturaCm / frente.ext.alt, escP = alturaCm / perfil.ext.alt;
  const medidas = {};
  for (const k of ['pescoco', 'cintura', 'abdomen', 'quadril']) {
    const f = frente.niveis[k], p = perfil.niveis[k];
    if (!f || !p) { medidas[k] = null; continue; }
    const larg = f.larg * escF, prof = p.larg * escP;
    medidas[k] = { larg, prof, circ: perimetroElipse(larg, prof) };
  }
  const c = Object.fromEntries(Object.entries(medidas).map(([k, v]) => [k, v && v.circ]));
  const gord = marinha(sexo, alturaCm, c);
  return { medidas, gordura: gord != null && isFinite(gord) ? gord : null };
}

// ---------- MediaPipe (navegador) ----------

let detector = null;
async function carregar() {
  if (detector) return detector;
  const { PoseLandmarker, FilesetResolver } = await import(`${MP_URL}/vision_bundle.mjs`);
  const arquivos = await FilesetResolver.forVisionTasks(`${MP_URL}/wasm`);
  detector = await PoseLandmarker.createFromOptions(arquivos, {
    baseOptions: { modelAssetPath: MODELO, delegate: 'CPU' },
    runningMode: 'IMAGE', numPoses: 1, outputSegmentationMasks: true,
  });
  return detector;
}

// arquivo de foto -> canvas com no máximo 1600 px de altura (fotos de celular têm 4000 px ou mais)
export function abrirFoto(arquivo) {
  return new Promise((ok, erro) => {
    const url = URL.createObjectURL(arquivo), img = new Image();
    img.onload = () => {
      const k = Math.min(1, 1600 / img.naturalHeight), c = document.createElement('canvas');
      c.width = Math.round(img.naturalWidth * k); c.height = Math.round(img.naturalHeight * k);
      c.getContext('2d').drawImage(img, 0, 0, c.width, c.height);
      URL.revokeObjectURL(url); ok(c);
    };
    img.onerror = () => { URL.revokeObjectURL(url); erro(new Error('Não consegui abrir esta imagem.')); };
    img.src = url;
  });
}

// foto (canvas) -> { mask (Uint8Array), w, h, pts em pixels }
export async function detectar(img) {
  const det = await carregar();
  const r = det.detect(img);
  if (!r.landmarks || !r.landmarks.length) throw new Error('Não encontrei uma pessoa inteira nesta foto.');
  const w = img.width, h = img.height;
  const m = r.segmentationMasks[0], mw = m.width, mh = m.height, f = m.getAsFloat32Array();
  // a máscara pode vir em outra resolução: reamostra para o tamanho da foto
  const mask = new Uint8Array(w * h);
  for (let y = 0; y < h; y++) {
    const my = Math.min(mh - 1, Math.floor(y * mh / h));
    for (let x = 0; x < w; x++) mask[y * w + x] = f[my * mw + Math.min(mw - 1, Math.floor(x * mw / w))] > 0.5 ? 1 : 0;
  }
  m.close?.();
  const pts = r.landmarks[0].map(p => ({ x: p.x * w, y: p.y * h, visibility: p.visibility }));
  return { mask, w, h, pts };
}

// desenha a foto com as linhas medidas (para conferir)
export function desenhar(canvas, img, med, rotulos) {
  const w = img.width, h = img.height, k = Math.min(1, 900 / h);
  canvas.width = Math.round(w * k); canvas.height = Math.round(h * k);
  const ctx = canvas.getContext('2d');
  ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
  ctx.lineWidth = 3; ctx.font = 'bold 14px sans-serif';
  const cores = { pescoco: '#3F88C5', cintura: '#E4572E', abdomen: '#E6A23C', quadril: '#1A9E8F' };
  for (const [nome, t] of Object.entries(med.niveis)) {
    if (!t) continue;
    ctx.strokeStyle = ctx.fillStyle = cores[nome];
    ctx.beginPath(); ctx.moveTo(t.a * k, t.y * k); ctx.lineTo(t.b * k, t.y * k); ctx.stroke();
    ctx.fillText(rotulos[nome], (t.b + 6) * k, t.y * k + 5);
  }
  ctx.strokeStyle = 'rgba(255,255,255,.8)'; ctx.setLineDash([6, 6]);
  for (const y of [med.ext.topo, med.ext.base]) { ctx.beginPath(); ctx.moveTo(0, y * k); ctx.lineTo(canvas.width, y * k); ctx.stroke(); }
  ctx.setLineDash([]);
}
