"""
Simulação 2D da dispersão de um poluente no Lago Paranoá (Brasília-DF)
usando as Equações de Água Rasa (Shallow Water Equations) integradas na
vertical, com PROFUNDIDADE CONSTANTE, acopladas a uma equação de
advecção-difusão-decaimento para o poluente.

Geometria: contorno REAL do lago obtido do OpenStreetMap (relação OSM
2758139, "Lago Paranoá", via API Nominatim), incluindo as ilhas.
Dados © OpenStreetMap contributors, licença ODbL.
O contorno é baixado na 1ª execução e guardado em 'paranoa_osm.geojson'.

ATENÇÃO — modelo DIDÁTICO:
  * Profundidade constante (parâmetro 'prof'); o lago real tem batimetria
    variável.
  * Posições de afluentes, barragem, lançamento e pontos de monitoramento são
    APROXIMADAS (colocadas nas pontas dos braços / pontos plausíveis).
    Confira no mapa 01_mapa.png e corrija as coordenadas se necessário.
  * Vazões, vento e cargas são valores ILUSTRATIVOS de ordem de grandeza.

Física:
  ∂η/∂t + ∂(Hu)/∂x + ∂(Hv)/∂y = S_vol                       (continuidade)
  ∂u/∂t = -g ∂η/∂x + f v - Cd|U|u/H + τx/(ρH) + ν∇²u         (momento x)
  ∂v/∂t = -g ∂η/∂y - f u - Cd|U|v/H + τy/(ρH) + ν∇²v         (momento y)
  ∂(HC)/∂t + ∇·(HUC) = ∇·(H Kh ∇C) - k H C + fontes           (poluente)

  η = elevação da superfície, h = profundidade em repouso (constante),
  H = h + η. Advecção não-linear do momento omitida (correntes muito fracas).
  Com profundidade constante, a corrente média gerada pelo vento é pequena
  (o vento principalmente inclina a superfície); o transporte do poluente é
  dominado pelo fluxo afluentes → barragem e pela difusão turbulenta.

Numérica: grade C de Arakawa, esquema explícito "forward-backward",
atrito de fundo semi-implícito, transporte do poluente upwind conservativo
(volumes finitos: conserva massa e não gera concentrações negativas).

Dependências: numpy, matplotlib (pillow opcional, para o GIF).
    pip install numpy matplotlib pillow
"""

import os
import json
import time
import urllib.request
from collections import deque

import numpy as np
import matplotlib.pyplot as plt
from matplotlib import animation
from matplotlib.colors import LogNorm
from matplotlib.path import Path

# =============================================================================
# 1. PARÂMETROS (edite aqui)
# =============================================================================
CFG = dict(
    # --- grade e tempo ---
    dx=100.0,                 # resolução (m)
    t_final=6 * 86400.0,      # duração (s)
    cfl=0.5,                  # fator de segurança do passo de tempo
    saida_cada=6 * 3600.0,    # intervalo entre quadros salvos (s)

    # --- física ---
    g=9.81,
    latitude=-15.8,           # Brasília (graus)
    prof=12.0,                # profundidade constante (m) [aprox.]
    cd_fundo=2.5e-3,          # coef. de atrito de fundo (quadrático)
    nu=5.0,                   # viscosidade turbulenta horizontal (m²/s)
    Kh=5.0,                   # difusividade turbulenta horizontal (m²/s)
    decaimento=0.2,           # decaimento de 1ª ordem (1/dia); 0 = conservativo

    # --- vento (convenção meteorológica: direção DE ONDE sopra) ---
    vento_vel=5.0,            # m/s a 10 m
    vento_dir=90.0,           # graus (90 = vento de leste) [ilustrativo]
    rho_ar=1.2, rho_agua=1000.0, cd_vento=1.3e-3,
    rampa_vento=6 * 3600.0,   # liga o vento gradualmente (evita choque/seiche)

    # --- poluente ---
    # 'continuo': lançamento contínuo (ex.: efluente de ETE)
    # 'derrame' : massa instantânea no instante t=0 (ex.: acidente)
    modo='continuo',
    fonte_lonlat=(-47.884, -15.833),  # braço do Riacho Fundo [aprox.]
    Q_fonte=1.5,              # vazão do efluente (m³/s) [ilustrativo]
    C_fonte=100.0,            # concentração no efluente (mg/L = g/m³)
    massa_derrame=5e6,        # massa no modo 'derrame' (g)
    duracao_fonte=None,       # s; None = lança durante toda a simulação

    # --- geometria ---
    osm_id='R2758139',        # relação OSM do Lago Paranoá
    arquivo_contorno='paranoa_osm.geojson',

    # --- saída ---
    pasta_saida='saida_paranoa',
    escala_log=True,          # mapas de concentração em escala logarítmica
    gerar_gif=True,
)

# Afluentes: (lon, lat) aproximados nas pontas dos braços, vazão (m³/s) ilustrativa.
AFLUENTES = {
    'Riacho Fundo':      ((-47.905, -15.842), 2.0),
    'Ribeirão do Gama':  ((-47.872, -15.857), 1.5),
    'Ribeirão Bananal':  ((-47.896, -15.729), 1.0),
    'Ribeirão do Torto': ((-47.855, -15.726), 2.5),
}
BARRAGEM_LONLAT = (-47.786, -15.798)   # extremo leste [aprox.]

# Pontos de monitoramento (lon, lat)
PONTOS = {
    'P1 braço R. Fundo': (-47.866, -15.825),
    'P2 corpo central':  (-47.821, -15.807),
    'P3 braço norte':    (-47.852, -15.762),
    'P4 barragem':       (-47.800, -15.796),
}

R_TERRA = 6_371_000.0


# =============================================================================
# 2. GEOMETRIA REAL (OpenStreetMap)
# =============================================================================
def obter_contorno_osm(cfg):
    """Retorna a geometria GeoJSON (Polygon/MultiPolygon) do lago.
    Usa o arquivo em cache se existir; senão baixa do Nominatim (OSM)."""
    arq = cfg['arquivo_contorno']
    if os.path.exists(arq):
        with open(arq) as fh:
            return json.load(fh)
    url = ('https://nominatim.openstreetmap.org/lookup?osm_ids='
           f"{cfg['osm_id']}&format=json&polygon_geojson=1")
    print('Baixando contorno do lago do OpenStreetMap (Nominatim)...')
    req = urllib.request.Request(url, headers={'User-Agent': 'lake-dispersion-sim/1.0'})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            dados = json.load(r)
    except Exception as e:
        raise SystemExit(f'Não foi possível baixar o contorno ({e}). Verifique a '
                         f'conexão ou coloque um GeoJSON em {arq}.')
    if not dados:
        raise SystemExit('Nominatim não retornou geometria para ' + cfg['osm_id'])
    geo = dados[0]['geojson']
    with open(arq, 'w') as fh:
        json.dump(geo, fh)
    return geo


class Projecao:
    """lon/lat -> metros locais (equiretangular; erro desprezível em ~15 km)."""
    def __init__(self, lon0, lat0):
        self.lon0, self.lat0 = lon0, lat0
        self.kx = R_TERRA * np.cos(np.deg2rad(lat0)) * np.pi / 180
        self.ky = R_TERRA * np.pi / 180

    def __call__(self, lon, lat):
        return (np.asarray(lon) - self.lon0) * self.kx, (np.asarray(lat) - self.lat0) * self.ky


def _maior_componente(m):
    """Mantém apenas o maior conjunto conexo (vizinhança 4) de células True."""
    rot = -np.ones(m.shape, int)
    tamanhos = []
    ny, nx = m.shape
    for j0, i0 in zip(*np.nonzero(m)):
        if rot[j0, i0] >= 0:
            continue
        k = len(tamanhos); rot[j0, i0] = k; fila = deque([(j0, i0)]); n = 0
        while fila:
            j, i = fila.popleft(); n += 1
            for jj, ii in ((j+1, i), (j-1, i), (j, i+1), (j, i-1)):
                if 0 <= jj < ny and 0 <= ii < nx and m[jj, ii] and rot[jj, ii] < 0:
                    rot[jj, ii] = k; fila.append((jj, ii))
        tamanhos.append(n)
    return rot == int(np.argmax(tamanhos))


def construir_lago(cfg):
    """Retorna X, Y (centros de célula, m), máscara molhada, h (m), projeção e
    anéis do contorno em metros (para desenhar)."""
    if cfg.get('contorno_utm'):
        # contorno já em metros (UTM), como o do Cordel: um anel sem ilhas
        with open(cfg['contorno_utm']) as fh:
            anel = np.array(json.load(fh)['contorno'], float)
        poligonos = [[anel.tolist()]]
        x0, y0 = anel.min(0)
        proj = lambda x, y: (np.asarray(x) - x0, np.asarray(y) - y0)
    else:
        geo = obter_contorno_osm(cfg)
        poligonos = [geo['coordinates']] if geo['type'] == 'Polygon' else geo['coordinates']
        todos = np.vstack([np.array(p[0]) for p in poligonos])
        proj = Projecao(todos[:, 0].min(), todos[:, 1].min())

    dx = cfg['dx']; borda = 2 * dx
    aneis = [[np.column_stack(proj(np.array(r)[:, 0], np.array(r)[:, 1])) for r in p]
             for p in poligonos]
    xmax = max(a[0][:, 0].max() for a in aneis); ymax = max(a[0][:, 1].max() for a in aneis)
    for p in aneis:                      # desloca para deixar margem seca
        for a in p:
            a += borda
    nx, ny = int(np.ceil((xmax + 2 * borda) / dx)), int(np.ceil((ymax + 2 * borda) / dx))
    x = (np.arange(nx) + 0.5) * dx; y = (np.arange(ny) + 0.5) * dx
    X, Y = np.meshgrid(x, y)
    pts = np.column_stack([X.ravel(), Y.ravel()])

    molhado = np.zeros(X.size, bool)
    for p in aneis:
        dentro = Path(p[0]).contains_points(pts)
        for ilha in p[1:]:
            dentro &= ~Path(ilha).contains_points(pts)
        molhado |= dentro
    molhado = molhado.reshape(X.shape)
    molhado[0, :] = molhado[-1, :] = molhado[:, 0] = molhado[:, -1] = False
    molhado = _maior_componente(molhado)

    h = np.where(molhado, cfg['prof'], 0.0)
    # projeção com o deslocamento da margem embutido
    proj_final = lambda lon, lat: tuple(c + borda for c in proj(lon, lat))
    return X, Y, molhado, h, proj_final, aneis


def indice_celula(xy, X, Y, molhado):
    """Célula molhada mais próxima de um ponto (x, y) em metros."""
    d = np.hypot(X - xy[0], Y - xy[1])
    d[~molhado] = np.inf
    return np.unravel_index(np.argmin(d), d.shape)


# =============================================================================
# 3. MODELO
# =============================================================================
def laplaciano(a, dx):
    return (np.roll(a, 1, 0) + np.roll(a, -1, 0) +
            np.roll(a, 1, 1) + np.roll(a, -1, 1) - 4.0 * a) / dx**2


def simular(cfg=CFG):
    os.makedirs(cfg['pasta_saida'], exist_ok=True)
    X, Y, wet, h, proj, aneis = construir_lago(cfg)
    ny, nx = h.shape
    dx, g = cfg['dx'], cfg['g']
    area = dx * dx

    print(f"Grade: {nx} x {ny} células, {wet.sum()} molhadas")
    print(f"Área do lago (raster): {wet.sum() * area / 1e6:.1f} km² | "
          f"profundidade constante: {cfg['prof']:.1f} m | "
          f"volume: {(h[wet].sum() * area) / 1e6:.0f} hm³")

    # converte posições lon/lat -> metros
    # afluentes: (posição, Q) ou (posição, Q, C da água que entra)
    afluentes = cfg.get('afluentes') or AFLUENTES
    afl_xy = {n: (proj(*a[0]), a[1]) for n, a in afluentes.items()}
    C_afl = {n: (a[2] if len(a) > 2 else 0.0) for n, a in afluentes.items()}
    barr_xy = proj(*cfg.get('barragem', BARRAGEM_LONLAT))
    fonte_xy = proj(*cfg['fonte_lonlat'])
    pontos = cfg.get('pontos') or PONTOS
    pontos_xy = {n: proj(*ll) for n, ll in pontos.items()}

    # máscaras das faces (grade C): face aberta só se as 2 células são água
    mu = np.zeros((ny, nx + 1), bool); mu[:, 1:-1] = wet[:, :-1] & wet[:, 1:]
    mv = np.zeros((ny + 1, nx), bool); mv[1:-1, :] = wet[:-1, :] & wet[1:, :]

    # estado
    eta = np.zeros((ny, nx))
    u = np.zeros((ny, nx + 1))
    v = np.zeros((ny + 1, nx))
    C = np.zeros((ny, nx))                    # g/m³ (= mg/L)

    f = 2 * 7.2921e-5 * np.sin(np.deg2rad(cfg['latitude']))

    # tensão do vento (N/m²); direção meteorológica -> vetor "para onde vai"
    ang = np.deg2rad(cfg['vento_dir'])
    Wx, Wy = -cfg['vento_vel'] * np.sin(ang), -cfg['vento_vel'] * np.cos(ang)
    W = np.hypot(Wx, Wy)
    taux = cfg['rho_ar'] * cfg['cd_vento'] * W * Wx
    tauy = cfg['rho_ar'] * cfg['cd_vento'] * W * Wy

    # fontes/sumidouros de volume (m³/s por célula)
    Qsrc = np.zeros((ny, nx))
    QCsrc = np.zeros((ny, nx))                # carga dos afluentes (g/s)
    for nome, (xy, Q) in afl_xy.items():
        Qsrc[indice_celula(xy, X, Y, wet)] += Q
        QCsrc[indice_celula(xy, X, Y, wet)] += Q * C_afl[nome]
    rampa_Q = cfg.get('rampa_vazao', 0.0)     # vazões crescem de 0 ao nominal (1 - cos)
    fator_Q = lambda t: 0.5 * (1 - np.cos(np.pi * min(t / rampa_Q, 1.0))) if rampa_Q > 0 else 1.0
    dias_mapas = sorted(cfg.get('instantes_dias', ()))
    mapas = {}
    jf, if_ = indice_celula(fonte_xy, X, Y, wet)
    jb, ib = indice_celula(barr_xy, X, Y, wet)
    Q_ete = cfg['Q_fonte'] if cfg['modo'] == 'continuo' else 0.0

    if cfg['modo'] == 'derrame':
        C[jf, if_] = cfg['massa_derrame'] / (h[jf, if_] * area)

    k_dec = cfg['decaimento'] / 86400.0

    dt = cfg['cfl'] * dx / np.sqrt(2 * g * h.max())
    nsteps = int(np.ceil(cfg['t_final'] / dt))
    print(f"dt = {dt:.2f} s, {nsteps} passos")

    pontos_idx = {n: indice_celula(xy, X, Y, wet) for n, xy in pontos_xy.items()}
    serie_cada = max(20, nsteps // 10000)     # ~10⁴ pontos nas séries, qualquer duração
    serie_t, serie_C = [], {n: [] for n in pontos}
    serie_massa, serie_saiu, serie_entrou = [], [], []
    quadros = []            # (t, C, u_c, v_c)
    massa_lancada = cfg['massa_derrame'] if cfg['modo'] == 'derrame' else 0.0
    massa_saiu = 0.0
    massa_decaiu = 0.0
    prox_saida = 0.0
    t = 0.0
    t0 = time.time()
    n0, t_parede_antes = 0, 0.0
    ck = cfg.get('checkpoint')
    if ck and cfg.get('continuar'):
        if not os.path.exists(ck):
            raise SystemExit(f'--continuar: checkpoint {ck} não encontrado')
        E = np.load(ck, allow_pickle=False)
        n0, t, prox_saida = int(E['n']) + 1, float(E['t']), float(E['prox_saida'])
        eta, u, v, C = E['eta'].copy(), E['u'].copy(), E['v'].copy(), E['C'].copy()
        massa_lancada, massa_saiu, massa_decaiu = (float(E[k]) for k in ('massa_lancada', 'massa_saiu', 'massa_decaiu'))
        t_parede_antes = float(E['t_parede'])
        serie_t = list(E['serie_t']); serie_massa = list(E['serie_massa'])
        serie_saiu = list(E['serie_saiu']); serie_entrou = list(E['serie_entrou'])
        for k, nome in enumerate(serie_C):
            serie_C[nome] = list(E['sondas'][:, k])
        mapas = {d: E[f'mapa_{d}'] for d in dias_mapas if f'mapa_{d}' in E.files}
        quadros = [(float(tq), Cq, uq, vq) for tq, Cq, uq, vq in
                   zip(E['quadros_t'], E['quadros_C'], E['quadros_u'], E['quadros_v'])]
        print(f"Retomando do checkpoint: passo {n0} de {nsteps}, t = {t / 86400:.2f} dias "
              f"({t_parede_antes:.0f} s de parede antes)")

    def gravar_checkpoint(n):
        """Estado depois do passo n (a retomada segue do passo n + 1), gravado de forma atômica."""
        tmp = ck + '.tmp.npz'
        np.savez_compressed(
            tmp, n=n, t=t, prox_saida=prox_saida, eta=eta, u=u, v=v, C=C,
            massa_lancada=massa_lancada, massa_saiu=massa_saiu, massa_decaiu=massa_decaiu,
            t_parede=t_parede_antes + time.time() - t0, serie_t=np.array(serie_t),
            serie_massa=np.array(serie_massa), serie_saiu=np.array(serie_saiu),
            serie_entrou=np.array(serie_entrou), sondas=np.array([serie_C[k] for k in serie_C]).T,
            quadros_t=np.array([q[0] for q in quadros]), quadros_C=np.array([q[1] for q in quadros]),
            quadros_u=np.array([q[2] for q in quadros]), quadros_v=np.array([q[3] for q in quadros]),
            **{f'mapa_{d}': c for d, c in mapas.items()})
        os.replace(tmp, ck)

    parar_s = cfg.get('parar_apos_h', 0) * 3600.0
    prox_ck = time.time() + 1800.0

    for n in range(n0, nsteps + 1):
        # ---------------- saídas ----------------
        if t >= prox_saida - 1e-9:
            uc = 0.5 * (u[:, 1:] + u[:, :-1]); vc = 0.5 * (v[1:, :] + v[:-1, :])
            quadros.append((t, C.copy(), uc, vc))
            prox_saida += cfg['saida_cada']
        if n % serie_cada == 0:
            serie_t.append(t)
            for nome, (j, i) in pontos_idx.items():
                serie_C[nome].append(C[j, i])
            serie_massa.append((C * np.where(wet, h + eta, 0) * area).sum())
            serie_saiu.append(massa_saiu); serie_entrou.append(massa_lancada)
        for d in dias_mapas:
            if d not in mapas and t >= d * 86400.0 - 1e-6:
                mapas[d] = C.copy()
        if n == nsteps:
            break

        H = np.where(wet, h + eta, 0.0)
        Hu = np.zeros_like(u); Hu[:, 1:-1] = 0.5 * (H[:, :-1] + H[:, 1:])
        Hv = np.zeros_like(v); Hv[1:-1, :] = 0.5 * (H[:-1, :] + H[1:, :])

        # ---------------- continuidade ----------------
        Fx = Hu * u * mu        # transporte (m²/s) nas faces x
        Fy = Hv * v * mv
        fonte_ativa = (cfg['modo'] == 'continuo' and
                       (cfg['duracao_fonte'] is None or t < cfg['duracao_fonte']))
        rQ = fator_Q(t)
        S = rQ * Qsrc
        if fonte_ativa:
            S[jf, if_] += Q_ete
        Q_saida = rQ * Qsrc.sum() + (Q_ete if fonte_ativa else 0.0)   # nível médio constante
        S[jb, ib] -= Q_saida
        V_old = H * area
        eta = eta - dt * ((Fx[:, 1:] - Fx[:, :-1]) / dx + (Fy[1:, :] - Fy[:-1, :]) / dx) \
                  + dt * S / area
        eta[~wet] = 0.0

        # ---------------- poluente (volumes finitos, upwind) ----------------
        M = C * V_old                                   # massa (g)
        Cl, Cr = np.zeros_like(u), np.zeros_like(u)
        Cl[:, 1:-1], Cr[:, 1:-1] = C[:, :-1], C[:, 1:]
        Cb, Ct = np.zeros_like(v), np.zeros_like(v)
        Cb[1:-1, :], Ct[1:-1, :] = C[:-1, :], C[1:, :]
        Gx = (Fx * np.where(Fx > 0, Cl, Cr) - cfg['Kh'] * Hu * (Cr - Cl) / dx * mu) * dx
        Gy = (Fy * np.where(Fy > 0, Cb, Ct) - cfg['Kh'] * Hv * (Ct - Cb) / dx * mv) * dx
        M = M - dt * ((Gx[:, 1:] - Gx[:, :-1]) + (Gy[1:, :] - Gy[:-1, :]))
        if fonte_ativa:
            dm = cfg['C_fonte'] * Q_ete * dt
            M[jf, if_] += dm; massa_lancada += dm
        if rQ > 0 and QCsrc.any():
            M += rQ * QCsrc * dt; massa_lancada += rQ * QCsrc.sum() * dt
        saida = min(Q_saida * C[jb, ib] * dt, M[jb, ib])
        M[jb, ib] -= saida; massa_saiu += saida
        perda = M * (1 - np.exp(-k_dec * dt)); M -= perda; massa_decaiu += perda.sum()

        Hn = np.where(wet, h + eta, 0.0)
        C = np.where(wet, M / np.maximum(Hn * area, 1e-9), 0.0)
        C = np.maximum(C, 0.0)

        # ---------------- momento (com eta novo: forward-backward) ----------------
        rampa = min(1.0, t / cfg['rampa_vento']) if cfg['rampa_vento'] > 0 else 1.0
        Hu = np.zeros_like(u); Hu[:, 1:-1] = 0.5 * (Hn[:, :-1] + Hn[:, 1:])
        Hv = np.zeros_like(v); Hv[1:-1, :] = 0.5 * (Hn[:-1, :] + Hn[1:, :])

        # u
        v_u = np.zeros_like(u)
        v_u[:, 1:-1] = 0.25 * (v[:-1, :-1] + v[1:, :-1] + v[:-1, 1:] + v[1:, 1:])
        dedx = np.zeros_like(u); dedx[:, 1:-1] = (eta[:, 1:] - eta[:, :-1]) / dx
        Hu_s = np.maximum(Hu, 0.1)
        rhs = (-g * dedx + f * v_u + rampa * taux / (cfg['rho_agua'] * Hu_s)
               + cfg['nu'] * laplaciano(u * mu, dx))
        atr = cfg['cd_fundo'] * np.hypot(u, v_u) / Hu_s
        u = np.where(mu, (u + dt * rhs) / (1 + dt * atr), 0.0)

        # v (usa u já atualizado -> Coriolis mais estável)
        u_v = np.zeros_like(v)
        u_v[1:-1, :] = 0.25 * (u[:-1, :-1] + u[:-1, 1:] + u[1:, :-1] + u[1:, 1:])
        dedy = np.zeros_like(v); dedy[1:-1, :] = (eta[1:, :] - eta[:-1, :]) / dx
        Hv_s = np.maximum(Hv, 0.1)
        rhs = (-g * dedy - f * u_v + rampa * tauy / (cfg['rho_agua'] * Hv_s)
               + cfg['nu'] * laplaciano(v * mv, dx))
        atr = cfg['cd_fundo'] * np.hypot(v, u_v) / Hv_s
        v = np.where(mv, (v + dt * rhs) / (1 + dt * atr), 0.0)

        t += dt
        if ck and (time.time() >= prox_ck or (parar_s and time.time() - t0 >= parar_s)):
            gravar_checkpoint(n)
            prox_ck = time.time() + 1800.0
            if parar_s and time.time() - t0 >= parar_s:
                print(f"Parado após {parar_s / 3600:g} h de parede no passo {n + 1} de {nsteps} "
                      f"(t = {t / 86400:.2f} dias); checkpoint em {ck}. Retome com --continuar.",
                      flush=True)
                raise SystemExit(3)
        if n % 10000 == 0 and n > 0:
            vel = np.hypot(0.5 * (u[:, 1:] + u[:, :-1]), 0.5 * (v[1:, :] + v[:-1, :]))
            print(f"  t = {t/3600:6.1f} h | |U|max = {vel.max():.4f} m/s | "
                  f"η = [{eta[wet].min()*100:.2f}, {eta[wet].max()*100:.2f}] cm | "
                  f"Cmax = {C.max():.2f} mg/L | {time.time()-t0:.0f} s")

    massa_lago = (C * np.where(wet, h + eta, 0) * area).sum()
    erro = massa_lancada - massa_lago - massa_saiu - massa_decaiu
    print(f"\nMassa lançada: {massa_lancada/1e6:.3f} t | no lago: {massa_lago/1e6:.3f} t | "
          f"saiu pela barragem: {massa_saiu/1e6:.3f} t | decaiu: {massa_decaiu/1e6:.3f} t")
    print(f"Erro de conservação: {erro/max(massa_lancada,1e-12)*100:.2e} %")
    t_parede = t_parede_antes + time.time() - t0
    print(f"Tempo de parede: {t_parede:.1f} s, {nsteps} passos, {t_parede / max(nsteps, 1) * 1e3:.3f} ms/passo")
    uc = 0.5 * (u[:, 1:] + u[:, :-1]); vc = 0.5 * (v[1:, :] + v[:-1, :])
    origem = np.zeros(2)
    if cfg.get('contorno_utm'):           # coordenadas da grade -> UTM
        with open(cfg['contorno_utm']) as fh:
            origem = np.array(json.load(fh)['contorno'], float).min(0) - 2 * dx
    np.savez(os.path.join(cfg['pasta_saida'], 'resultados.npz'),
             x=X[0] + origem[0], y=Y[:, 0] + origem[1], wet=wet, C=C, u=uc, v=vc, eta=eta,
             dt=dt, nsteps=nsteps, t_parede=t_parede, t_final=t,
             massa_lancada=massa_lancada, massa_lago=massa_lago, massa_saiu=massa_saiu,
             massa_decaiu=massa_decaiu, serie_t=np.array(serie_t),
             serie_massa=np.array(serie_massa), serie_saiu=np.array(serie_saiu),
             serie_entrou=np.array(serie_entrou), nomes_sondas=list(serie_C),
             sondas=np.array([serie_C[k] for k in serie_C]).T,
             dias_mapas=np.array(sorted(mapas)), **{f'C_{d}d': c for d, c in mapas.items()})

    return dict(X=X, Y=Y, wet=wet, h=h, aneis=aneis, quadros=quadros,
                serie_t=np.array(serie_t),
                serie_C={k: np.array(v) for k, v in serie_C.items()},
                afl_xy=afl_xy, barr_xy=barr_xy, fonte_xy=fonte_xy,
                pontos_xy=pontos_xy, cfg=cfg)


# =============================================================================
# 4. VISUALIZAÇÃO
# =============================================================================
ATRIB = '© OpenStreetMap contributors (ODbL)'


def _contorno(ax, aneis):
    for p in aneis:
        for a in p:
            ax.plot(a[:, 0] / 1e3, a[:, 1] / 1e3, 'k-', lw=0.6)


def _rodape(ax):
    ax.text(0.99, 0.01, ATRIB, transform=ax.transAxes, ha='right', va='bottom',
            fontsize=6, color='0.3')


def _tempo(t):
    """Rótulo de tempo em horas (até 2 dias) ou em dias."""
    return f't = {t / 3600:.0f} h' if t <= 2 * 86400 else f't = {t / 86400:.0f} dias'


def plotar(res):
    X, Y, wet = res['X'] / 1e3, res['Y'] / 1e3, res['wet']
    cfg = res['cfg']; out = cfg['pasta_saida']
    ny, nx = wet.shape
    ext = [0, nx * cfg['dx'] / 1e3, 0, ny * cfg['dx'] / 1e3]
    km = lambda xy: (xy[0] / 1e3, xy[1] / 1e3)

    # --- mapa: contorno real, afluentes, barragem, fonte, pontos ---
    fig, ax = plt.subplots(figsize=(7.5, 8))
    ax.imshow(np.where(wet, 1.0, np.nan), origin='lower', extent=ext, cmap='Blues',
              vmin=0, vmax=2)
    _contorno(ax, res['aneis'])
    for nome, (xy, Q) in res['afl_xy'].items():
        ax.plot(*km(xy), 'g^', ms=8)
        ax.annotate(f'{nome}\n({Q} m³/s)', km(xy), fontsize=7, xytext=(5, 3), textcoords='offset points')
    ax.plot(*km(res['barr_xy']), 'ks', ms=9)
    ax.annotate('Barragem', km(res['barr_xy']), fontsize=8, xytext=(-20, 10), textcoords='offset points')
    if cfg['modo'] != 'continuo' or cfg['Q_fonte'] > 0:
        ax.plot(*km(res['fonte_xy']), 'r*', ms=15, label='Lançamento')
    for nome, xy in res['pontos_xy'].items():
        ax.plot(*km(xy), 'o', mfc='none', mec='k')
        ax.annotate(nome.split()[0], km(xy), fontsize=8, xytext=(4, -10), textcoords='offset points')
    ax.set(title=f"Lago Paranoá — contorno OSM, profundidade constante {cfg['prof']:.0f} m",
           xlabel='x (km)', ylabel='y (km)', aspect='equal')
    if ax.get_legend_handles_labels()[0]:
        ax.legend(loc='upper right')
    _rodape(ax); fig.tight_layout()
    fig.savefig(f'{out}/01_mapa.png', dpi=150); plt.close(fig)

    # --- mapas de concentração ---
    quadros = res['quadros']
    idx = np.linspace(1, len(quadros) - 1, 4).astype(int)
    vmax = max(np.percentile(quadros[-1][1][wet], 99.9), 1e-2)
    norm = LogNorm(vmin=1e-3, vmax=vmax) if cfg['escala_log'] else plt.Normalize(0, vmax)
    mascara = lambda C: np.ma.masked_where(~wet | (cfg['escala_log'] & (C < 1e-3)), C)
    fig, axs = plt.subplots(2, 2, figsize=(12, 12.5))
    s = max(1, int(700 / cfg['dx']))
    for ax, k in zip(axs.flat, idx):
        t, C, uc, vc = quadros[k]
        ax.imshow(np.where(wet, 1.0, np.nan), origin='lower', extent=ext, cmap='Blues', vmin=0, vmax=6)
        im = ax.imshow(mascara(C), origin='lower', extent=ext, cmap='turbo', norm=norm)
        _contorno(ax, res['aneis'])
        m = wet[::s, ::s]
        # setas com escala fixa (2 mm/s = 1 km); limitadas a 3 mm/s para que o
        # escoamento local forte junto à barragem não esconda o resto
        us, vs = uc[::s, ::s][m], vc[::s, ::s][m]
        fat = np.minimum(1.0, 0.003 / np.maximum(np.hypot(us, vs), 1e-12))
        q = ax.quiver(X[::s, ::s][m], Y[::s, ::s][m], us * fat, vs * fat, color='0.25',
                      angles='xy', scale_units='xy', scale=0.002, width=0.0025)
        ax.quiverkey(q, 0.78, 0.95, 0.002, '2 mm/s', coordinates='axes')
        ax.set(title=_tempo(t), xlabel='x (km)', ylabel='y (km)', aspect='equal')
        plt.colorbar(im, ax=ax, label='C (mg/L)', shrink=0.75)
        _rodape(ax)
    fig.suptitle(f"Dispersão do poluente — vento {cfg['vento_vel']} m/s de {cfg['vento_dir']:.0f}°, "
                 f"Kh = {cfg['Kh']} m²/s" + (f" ({cfg['titulo']})" if cfg.get('titulo') else ""),
                 fontsize=14)
    fig.tight_layout(); fig.savefig(f'{out}/02_concentracao.png', dpi=150); plt.close(fig)

    # --- séries temporais ---
    fig, ax = plt.subplots(figsize=(9, 4.5))
    esc, unid = (3600, 'h') if res['serie_t'][-1] <= 2 * 86400 * 7 else (86400, 'dias')
    for nome, c in res['serie_C'].items():
        ax.plot(res['serie_t'] / esc, c, label=nome)
    ax.set(xlabel=f'Tempo ({unid})', ylabel='C (mg/L)', title='Concentração nos pontos de monitoramento')
    ax.grid(alpha=0.3); ax.legend(); fig.tight_layout()
    fig.savefig(f'{out}/03_series.png', dpi=150); plt.close(fig)

    # --- animação ---
    if cfg['gerar_gif']:
        fig, ax = plt.subplots(figsize=(7, 7.5))
        ax.imshow(np.where(wet, 1.0, np.nan), origin='lower', extent=ext, cmap='Blues', vmin=0, vmax=6)
        im = ax.imshow(mascara(quadros[0][1]), origin='lower', extent=ext, cmap='turbo', norm=norm)
        _contorno(ax, res['aneis']); _rodape(ax); ax.set_aspect('equal')
        plt.colorbar(im, ax=ax, label='C (mg/L)', shrink=0.75)
        tit = ax.set_title('')
        def upd(k):
            im.set_data(mascara(quadros[k][1])); tit.set_text(_tempo(quadros[k][0]))
            return im, tit
        try:
            anim = animation.FuncAnimation(fig, upd, frames=len(quadros), interval=300)
            anim.save(f'{out}/04_animacao.gif', writer=animation.PillowWriter(fps=4))
        except Exception as e:
            print('GIF não gerado:', e)
        plt.close(fig)
    print(f"Figuras salvas em ./{out}/")


# =============================================================================
# 5. CASO DO CORDEL (mesma física do caso 'paranoa' do repositório cordel)
# =============================================================================
def cfg_cordel(dias=7.0, dx=80.0, pasta='resultados/caso_cordel_7d', mapas=None,
               contorno='paranoa_contorno_cordel.json'):
    """Parâmetros do caso casos/paranoa.py do Cordel: contorno do Cordel (UTM 23S,
    sem ilhas), 5 afluentes com as vazões e posições de lá, C/C0 = 1 na água do
    Riacho Fundo, saída na barragem, nu = Kh = 0,1 m²/s, rampa de 1 dia nas
    vazões; sem vento, Coriolis, atrito de fundo nem decaimento."""
    with open(contorno) as fh:
        D = json.load(fh)
    E = D['entradas']
    vazoes = dict(bananal=1.5, torto=2.0, riacho_fundo=2.5, gama=2.0, cabeca_de_veado=0.5)
    c = dict(CFG)
    c.update(dx=dx, t_final=dias * 86400.0, saida_cada=dias * 86400.0 / 28,
             latitude=0.0, cd_fundo=0.0, nu=0.1, Kh=0.1, decaimento=0.0,
             vento_vel=0.0, rampa_vento=0.0, modo='continuo', Q_fonte=0.0,
             contorno_utm=contorno, pasta_saida=pasta, rampa_vazao=86400.0,
             afluentes={k: (E[k], Q, 1.0 if k == 'riacho_fundo' else 0.0) for k, Q in vazoes.items()},
             barragem=tuple(D['saida']), fonte_lonlat=tuple(E['riacho_fundo']),
             # nós das sondas do Cordel (no_central de casos/paranoa.py, malha h = 80 m)
             pontos={"Braço do Riacho Fundo": (190037.6, 8246848.2), "Braço Sul": (194857.4, 8247468.7),
                     "Corpo central": (197561.2, 8250827.5), "Braço Norte": (195427.9, 8255268.4),
                     "Barragem": (200550.9, 8251932.0)},
             instantes_dias=tuple(d for d in (mapas or ((1, 2, 4, 7) if dias <= 7 else (30, 90, 180, 365)))
                                  if d <= dias + 1e-9),
             titulo='caso do Cordel, C em C/C0')
    return c


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[1])
    ap.add_argument('--caso', choices=['padrao', 'cordel'], default='padrao',
                    help="'cordel': parâmetros do caso paranoa do repositório cordel")
    ap.add_argument('--dias', type=float, default=7.0, help='duração (caso cordel)')
    ap.add_argument('--dx', type=float, default=80.0, help='resolução em m (caso cordel)')
    ap.add_argument('--pasta', default=None, help='pasta de saída (caso cordel)')
    ap.add_argument('--mapas', default=None,
                    help='dias dos mapas gravados, ex. 30,90,180,365 (caso cordel; padrão: '
                         '1,2,4,7 até 7 dias e 30,90,180,365 acima)')
    ap.add_argument('--continuar', action='store_true',
                    help='retoma do checkpoint (<pasta>/checkpoint.npz) gravado por uma rodada anterior')
    ap.add_argument('--parar-apos', type=float, default=0.0, metavar='HORAS',
                    help='grava o checkpoint e para (código 3) após HORAS de tempo de parede')
    a = ap.parse_args()
    if a.caso == 'cordel':
        mapas = tuple(float(d) if '.' in d else int(d) for d in a.mapas.split(',')) if a.mapas else None
        cfg = cfg_cordel(a.dias, a.dx, a.pasta or f'resultados/caso_cordel_{a.dias:g}d', mapas)
    else:
        cfg = dict(CFG)
    # checkpoint: gravado a cada 30 min de parede e ao parar por --parar-apos
    cfg.update(checkpoint=os.path.join(cfg['pasta_saida'], 'checkpoint.npz'),
               continuar=a.continuar, parar_apos_h=a.parar_apos)
    resultado = simular(cfg)
    plotar(resultado)
