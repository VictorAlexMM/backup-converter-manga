# Manga Backup Converter (mangabackuputil)

[![GitHub Release](https://img.shields.io/github/v/release/VictorAlexMM/backup-converter-manga?style=flat-square)](https://github.com/VictorAlexMM/backup-converter-manga/releases)
[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg?style=flat-square)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green.svg?style=flat-square)](./LICENSE.md)

Ferramenta prática e rápida para converter backups de bibliotecas de mangás entre os principais aplicativos de leitura (Android, iOS e Desktop), preservando suas obras, capítulos lidos, categorias e progresso.

---

## 📌 Para que serve?

Se você já trocou de aplicativo de mangá (por exemplo, migrando do Android para o iOS ou mudando do Tachiyomi/Mihon para o Tachimanga, Aidoku ou Mangayomi), sabe como é difícil transferir centenas de títulos manualmente.

O **Manga Backup Converter** resolve esse problema convertendo o arquivo de backup de um aplicativo diretamente para o formato de outro, preservando:
- 📚 Lista de mangás e metadados
- 📑 Capítulos lidos e histórico de leitura
- 🏷️ Categorias e pastas personalizadas
- 🌟 Status de favoritos e rastreadores

### Formatos Suportados

| Aplicativo | Extensão |
| :--- | :--- |
| **Mihon / Tachiyomi** (e forks: SY, J2K, Yokai, Neko) | `.tachibk`, `.proto.gz` |
| **Tachimanga** (iOS/macOS) | `.tmb` |
| **Mangayomi** (Multiplataforma) | `.backup` |
| **Aidoku** (iOS) | `.aib` |
| **Paperback** (iOS) | `.pas4` |

---

## 🚀 Como Utilizar

Você pode usar o conversor de três formas: **Interface Gráfica (GUI)**, **Linha de Comando (CLI)** ou **Scripts Python**.

### 1. Interface Gráfica (GUI) — Recomendado

Ideal para quem prefere uma interface visual intuitiva:

1. **Abra o programa:**
   - Execute o arquivo `mangabackuputil.exe` diretamente (ou execute `python manga_backup_converter_gui.py`).
2. **Selecione o arquivo de backup:**
   - Arraste e solte o arquivo de backup diretamente na janela do aplicativo, ou clique em **"Procurar..."**.
3. **Escolha o formato de saída:**
   - Selecione o aplicativo de destino (ex.: *Mihon (.tachibk)* ou *Tachimanga (.tmb)*).
4. **Clique em "Converter":**
   - O novo arquivo convertido será gerado na mesma pasta do arquivo original (com sufixo `_converted`).

> **Dica no Windows:** Você também pode simplesmente arrastar o arquivo de backup e soltá-lo em cima do ícone do executável `mangabackuputil.exe` para abrir a interface já com o arquivo carregado!

---

### 2. Linha de Comando (CLI)

Perfeito para automações ou uso em terminal:

```sh
# Usando o executável:
mangabackuputil convert -b "meu_backup.tmb" -f mihon

# Ou via Python:
python mangabackuputil_cli.py convert -b "meu_backup.tmb" -f mihon
```

#### Opções de Linha de Comando:

```sh
mangabackuputil convert -b <caminho-do-backup> -f <formato-destino> [-o <caminho-saida>]
```

| Parâmetro | Descrição |
| :--- | :--- |
| `-b, --backup` | Caminho do arquivo de backup de origem (*obrigatório*) |
| `-f, --output-format` | Formato desejado: `mihon`, `tachimanga`, `mangayomi`, `aidoku`, `paperback` (*obrigatório*) |
| `-o, --output` | (Opcional) Caminho do arquivo de saída gerado |
| `-i, --input-format` | (Opcional) Forçar detecção de formato de entrada |
| `-v, --verbose` | Exibir mensagens detalhadas no terminal |

Para abrir a interface gráfica a partir da linha de comando:
```sh
mangabackuputil gui
```

---

### 3. Scripts Python Específicos

Se preferir rodar conversões diretas específicas via scripts:

- **Converter Tachimanga (.tmb) para Mihon (.tachibk):**
  ```sh
  python -c "import convert_tachimanga_to_mihon; convert_tachimanga_to_mihon.convert('backup.tmb', 'saida.tachibk')"
  ```
- **Converter Mihon (.tachibk) para Tachimanga (.tmb):**
  ```sh
  python -c "import convert_mihon_to_tachimanga; convert_mihon_to_tachimanga.convert('backup.tachibk', 'saida.tmb')"
  ```

---

## 🛠️ Instalação e Execução pelo Código-Fonte

Caso queira executar diretamente pelo código Python:

1. **Clone o repositório:**
   ```sh
   git clone https://github.com/VictorAlexMM/backup-converter-manga.git
   cd backup-converter-manga
   ```

2. **Instale as dependências:**
   ```sh
   pip install -r proto/requirements.txt
   ```
   *(Opcional para suporte a Drag and Drop no Windows)*:
   ```sh
   pip install windnd
   ```

3. **Inicie o conversor:**
   ```sh
   python manga_backup_converter_gui.py
   ```

---

## 💖 Agradecimentos e Créditos

Um agradecimento especial ao desenvolvedor **[getBoolean](https://github.com/getBoolean)** por idealizar e iniciar o projeto original **[manga_backup_converter](https://github.com/getBoolean/manga_backup_converter)**. 

A engenharia reversa dos esquemas de dados, definições dos arquivos `.proto` e as rotinas de conversão fundamentaram toda a base que possibilita a integração e liberdade dos leitores de mangá entre plataformas.

---

## 📄 Licença

Este projeto é distribuído sob a licença [MIT](./LICENSE.md).
