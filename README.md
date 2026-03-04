# YT Media Downloader

Aplicação para download de áudio e vídeo do YouTube com interface web local. Construída com FastAPI no backend e HTML/CSS/JS no frontend, rodando via Docker.

---

- Download de **áudio** nos formatos FLAC, MP3, M4A e OPUS
- Download de **vídeo** nos containers MP4, MKV
- Seleção de qualidade de vídeo carregada dinamicamente a partir do link
- Preview automático com thumbnail, título e duração ao colar o link
- Barra de progresso via Server-Sent Events
- Metadados e thumbnail embutidos no arquivo final

---

## Pré-requisitos

- Docker instalado e rodando

---

## Como rodar

```bash
docker compose up --build
```

Acesse no navegador: 

```
http://localhost:3001
```
(Remapear porta no docker compose caso necessário)



Para parar:

```bash
docker compose down
```

## Detalhes técnicos

### Backend (FastAPI + yt-dlp)

| Endpoint | Método | Descrição |
|---|---|---|
| `/info` | POST | Retorna metadados do vídeo e as qualidades disponíveis |
| `/download` | POST | Inicia download e transmite progresso via SSE |
| `/file/{file_id}` | GET | Retorna o arquivo gerado para download |

### Swagger UI

O FastAPI gera automaticamente a interface de documentação e testes interativos. Ela pode ser acessada em:
```
http://localhost:8000/docs
```
(Remapear porta no docker compose caso necessário)



### Frontend

O imput do formulário detecta automaticamente o link digitado e chama o `/info`. O download consome o stream do SSE atualizando a barra de progressão.

### Dependências principais
| Ferramenta | Função |
|---|---|
| [yt-dlp](https://github.com/yt-dlp/yt-dlp) | Download e extração de áudio/vídeo |
| [ffmpeg](https://ffmpeg.org) | Conversão de formatos e merge de streams |
| [FastAPI](https://fastapi.tiangolo.com) | Framework do servidor HTTP |
| [uvicorn](https://www.uvicorn.org) | Servidor ASGI |

