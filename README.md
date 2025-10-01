# Projeto-Louva-Deus  
🛒 **Descrições de Produtos E-commerce com Gemini + Streamlit**

## 📌 Visão Geral  
Aplicação em **Streamlit** que gera descrições de produtos para e-commerce usando a **Google Gemini API**.  
Cria textos em **HTML otimizados para SEO**, título e meta description, busca imagens **900x900**, processa dados de **EAN ou nome** e exporta resultados em **Excel**, facilitando a gestão de catálogos online.

A ferramenta cria:  
- Descrição detalhada em HTML (com seções de descrição, especificações e FAQ).  
- Título SEO otimizado (até 60 caracteres).  
- Meta description (até 350 caracteres).  
- Imagem do produto (900x900, fundo branco), baixada e processada automaticamente.  
- Exportação para Excel (.xlsx) com todas as informações.  

---

## 🚀 Funcionalidades  
- Geração de descrições em HTML com boas práticas de SEO.  
- Criação automática de títulos e meta descrições.  
- Busca de links de referência via **DuckDuckGo**.  
- Busca e processamento de imagens em **900x900** (canvas branco, sem distorção).  
- Identificação automática de produtos via **EAN ou nome**.  
- Exportação consolidada dos resultados para **Excel**.  
- Interface web simples e interativa via **Streamlit**.  

---

## 🛠️ Tecnologias Utilizadas  
- **Python 3.10+**  
- **Streamlit** → Interface web  
- **Google Gemini API** → Geração de conteúdo inteligente  
- **DuckDuckGo Search (ddgs)** → Busca de links e imagens  
- **Pandas** → Manipulação de dados  
- **Pillow (PIL)** → Processamento de imagens  
- **OpenPyXL** → Exportação Excel  

---

## ⚙️ Instalação  

Clone o repositório e instale as dependências:  
```bash
git clone https://github.com/seu-usuario/seu-repo.git
cd seu-repo
pip install -r requirements.txt
