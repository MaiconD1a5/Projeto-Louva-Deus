# app.py
# ------------------------------------------------------------
# Streamlit: Descrições E-commerce com Gemini + Título + Meta + Imagem 900x900
# ------------------------------------------------------------
import os
import re
import time, random
import unicodedata
from io import BytesIO
from typing import List, Dict, Tuple

import pandas as pd
import requests
import streamlit as st
import google.generativeai as genai
from PIL import Image  # pip install pillow

# Silenciar logs verbosos
os.environ.setdefault("GRPC_VERBOSITY", "NONE")
os.environ.setdefault("GLOG_minloglevel", "2")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

# ckDuckGoDu (ddgs)
try:
    from ddgs import DDGS  # pip install ddgs
except ImportError:
    st.stop()

# ----------------- Constantes -----------------
TITLE_MAX_CHARS = 60  # limite do título SEO
DEFAULT_IMG_DIR = os.path.join(os.path.expanduser("~"), "imagens_produtos")

# ----------------- Utils -----------------
def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text or "produto"

def build_product_id(ean: str, nome: str, idx: int = 1) -> str:
    """ID para arquivo: EAN se houver; senão slug do nome + idx."""
    if ean and ean.isdigit():
        return ean
    base = slugify(nome)
    return f"{base}-{idx:02d}"

def parse_linhas_produtos(texto: str) -> List[Tuple[str, str]]:
    """Transforma entrada em lista de (ean, nome)."""
    linhas = [l.strip() for l in texto.splitlines() if l.strip()]
    itens = []
    for l in linhas:
        ean = ""
        nome = l

        if " - " in l:
            partes = l.split(" - ", 1)
            if partes[0].strip().isdigit():
                ean = partes[0].strip()
                nome = partes[1].strip()
                itens.append((ean, nome))
                continue

        tokens = l.split()
        if tokens and tokens[0].isdigit() and len(tokens[0]) >= 8:
            ean = tokens[0]
            nome = " ".join(tokens[1:]).strip()
            itens.append((ean, nome if nome else ""))
            continue

        if l.isdigit():
            itens.append((l, ""))
            continue

        itens.append(("", l))
    return itens

def strip_code_fences(text: str) -> str:
    """Remove blocos ```...``` e rótulos (```html, ```markdown)."""
    if not isinstance(text, str):
        return ""
    text = re.sub(r"```[\w-]*\s*", "", text)
    text = text.replace("```", "")
    return text.strip()

def strip_tags(html: str) -> str:
    """Remove tags HTML para texto plano."""
    if not isinstance(html, str):
        return ""
    txt = re.sub(r"<[^>]+>", " ", html)
    txt = re.sub(r"\s+", " ", txt).strip()
    return txt

def buscar_links(consulta: str, qtd: int = 3) -> List[str]:
    """Busca links via DuckDuckGo (ddgs)."""
    urls: List[str] = []
    with DDGS() as ddgs_client:
        for item in ddgs_client.text(consulta, max_results=qtd):
            href = item.get("href")
            if href:
                urls.append(href)
    return urls

def buscar_imagens(consulta: str, qtd: int = 1) -> list[str]:
    """
    Busca URLs de imagens via DuckDuckGo (ddgs), compatível com variações de assinatura.
    """
    urls: list[str] = []
    try:
        with DDGS() as ddgs_client:
            gen_iter = None
            try:
                gen_iter = ddgs_client.images(consulta, max_results=qtd)
            except TypeError:
                gen_iter = ddgs_client.images(keywords=consulta, max_results=qtd)

            for item in gen_iter:
                href = item.get("image") or item.get("thumbnail") or item.get("url")
                if href:
                    urls.append(href)
                if len(urls) >= qtd:
                    break
    except Exception:
        pass
    return urls

def baixar_e_processar_imagem(url: str, pasta: str, nome_arquivo_sem_ext: str) -> tuple[str, str]:
    """
    Baixa imagem, converte para JPEG 900x900 (canvas branco, sem distorcer) e salva.
    Retorna (caminho_arquivo, url_origem) ou ("","") se falhar.
    """
    try:
        os.makedirs(pasta, exist_ok=True)
    except Exception:
        return "", ""

    try:
        r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        img_bytes = BytesIO(r.content)
        with Image.open(img_bytes) as im:
            if im.mode in ("RGBA", "P"):
                im = im.convert("RGB")

            target = (900, 900)
            im.thumbnail(target, Image.LANCZOS)

            canvas = Image.new("RGB", target, (255, 255, 255))
            x = (target[0] - im.width) // 2
            y = (target[1] - im.height) // 2
            canvas.paste(im, (x, y))

            out_path = os.path.join(pasta, f"{nome_arquivo_sem_ext}.jpg")
            canvas.save(out_path, "JPEG", quality=90, optimize=True, progressive=True)
            return out_path, url
    except Exception:
        return "", ""

def escolher_modelo_gemini() -> str:
    """Escolhe modelo Gemini que suporte generateContent."""
    preferencia = [
        "gemini-2.0-flash",
        "gemini-1.5-flash-001",
        "gemini-1.5-flash-latest",
        "gemini-1.5-flash",
        "gemini-1.5-pro-002",
        "gemini-1.5-pro",
    ]
    modelos = list(genai.list_models())
    suportados = [
        m for m in modelos
        if hasattr(m, "supported_generation_methods")
        and "generateContent" in getattr(m, "supported_generation_methods", [])
    ]
    if not suportados:
        raise RuntimeError("Nenhum modelo Gemini disponível com generateContent.")
    by_name = {m.name: m for m in suportados}
    for pref in preferencia:
        candidato = next((n for n in by_name if n.endswith(pref)), None)
        if candidato:
            return candidato
    return suportados[0].name

@st.cache_resource(show_spinner=False)
def get_gemini_model(api_key: str):
    genai.configure(api_key=api_key)
    nome = escolher_modelo_gemini()
    return genai.GenerativeModel(nome)

def perguntar_gemini(model, pergunta: str, max_retries: int = 5, base_sleep: float = 1.5) -> str:
    """Consulta Gemini com retries/backoff."""
    last_err = None
    for attempt in range(max_retries):
        try:
            resp = model.generate_content(pergunta, request_options={"timeout": 60})
            txt = getattr(resp, "text", "") or ""
            if txt.strip():
                return txt.strip()
            last_err = RuntimeError("Resposta vazia.")
            raise last_err
        except Exception as e:
            last_err = e
            sleep_s = base_sleep * (2 ** attempt) + random.uniform(0, 0.6)
            time.sleep(min(sleep_s, 12))
    return f"[Erro ao consultar o Gemini após {max_retries} tentativas: {last_err}]"

def montar_prompt(nome: str, ean: str, links: List[str]) -> str:
    """
    Instruímos o modelo a devolver:
      1) HTML
      2) TITLE: <título <= 60 chars>
      3) META_DESCRIPTION: <até 350 chars>
    """
    return f"""
Você é um redator sênior especializado em e-commerce (português do Brasil).
Tenho um site de e-commerce e preciso criar as MELHORES descrições para meus produtos.

Produto: {nome or 'Não informado'}
EAN: {ean or 'Não informado'}
Referências (apenas contexto; você NÃO acessa): {links}

TAREFA:
Crie a descrição do produto seguindo as MELHORES PRÁTICAS, **em HTML**, com esta estrutura:
1) <h2>Descrição</h2> ... (parágrafos)
2) <h2>Especificações</h2> ... (<ul><li>...</li></ul>)
3) <h2>Perguntas Frequentes</h2> ... (mínimo 4 pares <h3>pergunta</h3> + <p>resposta</p>)

SEO (obrigatório):
- Incluir exatamente 30 palavras-chave relevantes, embutidas naturalmente no texto (não criar lista separada).
- Usar apenas <h2> e <h3> (evitar <h1>).
- Se faltar informação, escreva "não informado".
- Gerar também um **Título SEO** conciso e rico em palavras-chave, com **no máximo {TITLE_MAX_CHARS} caracteres**.

FORMATO DE SAÍDA (STRICT, nesta ordem):
1) **APENAS O HTML** (sem cercar com ``` e sem comentários fora do HTML).
2) Em nova linha: TITLE: <título otimizado SEO, no máximo {TITLE_MAX_CHARS} caracteres>
3) Em nova linha: META_DESCRIPTION: <texto de até 350 caracteres, sem HTML>
"""

def separar_blocos(saida_modelo: str) -> tuple[str, str, str]:
    """
    Divide saída do modelo em (html, title, meta).
    Aceita:
      - HTML puro ou dentro de ```html
      - Linhas TITLE: e META_DESCRIPTION:
      - Fallback: <title>...</title> ou primeiro <h2>...</h2>
      - Fallback final: deriva de texto limpo
    """
    if not isinstance(saida_modelo, str):
        return "", "", ""

    raw = strip_code_fences(saida_modelo)

    # META_DESCRIPTION
    m_meta = re.search(
        r'^\s*(META_DESCRIPTION|META|META-DESCRIPTION)\s*:\s*(.*)$',
        raw, flags=re.IGNORECASE | re.MULTILINE
    )
    meta = ""
    before_meta = raw
    if m_meta:
        meta = m_meta.group(2).strip()
        before_meta = raw[:m_meta.start()].strip()

    # TITLE
    m_title = re.search(
        r'^\s*(TITLE|TITULO|TÍTULO)\s*:\s*(.*)$',
        before_meta, flags=re.IGNORECASE | re.MULTILINE
    )
    title = ""
    html_part = before_meta
    if m_title:
        title = m_title.group(2).strip()
        html_part = before_meta[:m_title.start()].strip()

    # <title>...</title>
    if not title:
        m_htitle = re.search(r"<\s*title\s*>\s*(.*?)\s*<\s*/\s*title\s*>",
                             html_part, flags=re.IGNORECASE | re.DOTALL)
        if m_htitle:
            title = re.sub(r"\s+", " ", m_htitle.group(1)).strip()

    # primeiro <h2>...</h2>
    if not title:
        m_h2 = re.search(r"<\s*h2\s*[^>]*>\s*(.*?)\s*<\s*/\s*h2\s*>",
                         html_part, flags=re.IGNORECASE | re.DOTALL)
        if m_h2:
            title = re.sub(r"\s+", " ", m_h2.group(1)).strip()

    # fallback: deriva do texto limpo
    if not title:
        plain = strip_tags(html_part)
        title = (plain[:TITLE_MAX_CHARS] or "Título do produto").strip()

    # corta tamanho
    if len(title) > TITLE_MAX_CHARS:
        title = title[:TITLE_MAX_CHARS].rstrip()

    # meta fallback
    if not meta:
        plain = strip_tags(html_part)
        meta = plain[:350].strip()

    html = html_part.strip() if html_part else raw.strip()
    return html, title, meta

def exportar_excel(df: pd.DataFrame) -> bytes:
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Produtos")
    buffer.seek(0)
    return buffer.getvalue()

# ----------------- UI -----------------
st.set_page_config(page_title="Descrições E-commerce (Gemini)", page_icon="🛒", layout="wide")
st.title("🛒 Descrições de Produtos com Gemini (HTML + Título + Meta + Imagem)")

with st.sidebar:
    st.subheader("Configurações")
    api_key = st.text_input(
        "Gemini API Key",
        value=os.getenv("GEMINI_API_KEY", ""),
        type="password"
    )
    qtd_links = st.slider("Links por produto", 1, 10, 3)
    baixar_img = st.checkbox("Baixar imagem principal (900x900 JPEG)", value=True)

    # Diretório de imagens seguro
    pasta_imgs = st.text_input(
        "Pasta para salvar imagens",
        value=DEFAULT_IMG_DIR,
        help=r"Ex.: C:\Users\rafae\imagens_produtos"
    )
    pasta_imgs = os.path.normpath(pasta_imgs)
    try:
        os.makedirs(pasta_imgs, exist_ok=True)
    except Exception as e:
        st.error(f"Erro ao criar pasta {pasta_imgs}: {e}")
        pasta_imgs = DEFAULT_IMG_DIR
        os.makedirs(pasta_imgs, exist_ok=True)

st.markdown("**Cole os produtos (um por linha)**. Exemplos:")
st.code(
    "7896009498299 - Corega Tabs Limpeza 3 Minutos\n"
    "7896009498299 Corega Tabs Limpeza 3 Minutos\n"
    "Corega Tabs Limpeza 3 Minutos\n"
    "7896009498299",
    language="text",
)
entrada = st.text_area("Produtos", height=180, placeholder="Cole aqui sua lista...")

col1, col2 = st.columns([1,1])
with col1: gerar = st.button("⚙️ Gerar descrições", use_container_width=True)
with col2: limpar = st.button("🧹 Limpar resultados", use_container_width=True)

# Estado
if "resultados" not in st.session_state or limpar:
    st.session_state["resultados"] = pd.DataFrame(
        columns=[
            "EAN", "Produto", "Links",
            "DescricaoHTML", "TitleSEO", "MetaDescription",
            "ImageFile", "ImageSourceURL"
        ]
    )

if gerar:
    if not api_key:
        st.error("Informe a API Key do Gemini na barra lateral.")
    elif not entrada.strip():
        st.error("Cole ao menos um produto.")
    else:
        # Modelo Gemini
        try:
            model = get_gemini_model(api_key)
        except Exception as e:
            st.error(f"Falha ao iniciar o Gemini: {e}")
            model = None

        if model:
            produtos = parse_linhas_produtos(entrada)
            progresso = st.progress(0)
            novos_registros = []

            for i, (ean, nome) in enumerate(produtos, start=1):
                consulta = " ".join([p for p in [ean, nome] if p]).strip()
                links = buscar_links(consulta or (ean or nome), qtd=qtd_links)

                prompt = montar_prompt(nome, ean, links)
                saida = perguntar_gemini(model, prompt)
                html, title, meta = separar_blocos(saida)

                img_saved = ""
                img_src = ""
                if baixar_img:
                    consulta_img = consulta or (ean or nome)
                    img_urls = buscar_imagens(consulta_img, qtd=3)
                    pid = build_product_id(ean, nome, i)
                    for url_img in img_urls:
                        saved, src = baixar_e_processar_imagem(url_img, pasta_imgs, pid)
                        if saved:
                            img_saved = saved
                            img_src = src
                            break

                novos_registros.append({
                    "EAN": ean,
                    "Produto": nome,
                    "Links": ", ".join(links),
                    "DescricaoHTML": html,
                    "TitleSEO": title,
                    "MetaDescription": meta,
                    "ImageFile": img_saved,
                    "ImageSourceURL": img_src
                })

                progresso.progress(i / max(1, len(produtos)))
                time.sleep(0.8)  # cortesia entre chamadas

            df_novos = pd.DataFrame(novos_registros)
            st.session_state["resultados"] = pd.concat(
                [st.session_state["resultados"], df_novos],
                ignore_index=True
            )
            st.success("Descrições, títulos, metas e imagens processados!")

st.subheader("Resultados")
df = st.session_state["resultados"]

if not df.empty:
    # Destacar títulos que passam do limite, por via das dúvidas
    def _flag_title_len(s: pd.Series) -> list[str]:
        styles = []
        for v in s:
            if isinstance(v, str) and len(v) > TITLE_MAX_CHARS:
                styles.append("background-color:#ffe5e5;")
            else:
                styles.append("")
        return styles

    st.dataframe(
        df.style.apply(_flag_title_len, subset=["TitleSEO"]),
        use_container_width=True,
        height=420
    )

    # Preview da última imagem salva (se houver)
    ult = df.iloc[-1]
    if ult.get("ImageFile"):
        st.markdown("### Pré-visualização da última imagem salva")
        try:
            st.image(ult["ImageFile"], width=240, caption=os.path.basename(ult["ImageFile"]))
        except Exception:
            pass

    excel_bytes = exportar_excel(df)
    st.download_button(
        label="⬇️ Baixar Excel (.xlsx)",
        data=excel_bytes,
        file_name="produtos_gemini.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True
    )
else:
    st.info("Nenhum resultado ainda. Gere para visualizar aqui.")
