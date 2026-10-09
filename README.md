# Painel de Separação

Painel em HTML (GitHub Pages) alimentado pelo XLSX diário que o ERP envia por e-mail.

## Como funciona

1. O ERP envia o `SEPARACAO_DIA_ANTERIOR.xlsx` para a conta Gmail.
2. Um **Google Apps Script** nessa conta roda de hora em hora, localiza os e-mails novos e grava cada anexo no repositório, em `dados/xlsx/`, com a data no nome (`2026-10-08_SEPARACAO.xlsx`). Nada é sobrescrito nem apagado: esse é o histórico.
3. A chegada do arquivo dispara o fluxo **Publicar painel** (GitHub Actions), que recalcula os indicadores de todo o histórico e publica o painel.

## Layout do arquivo

O painel lê as colunas pela posição, na ordem do relatório `relatorio_impressao_separacao.jrxml`:
data/hora da impressão, data, CODTIPOPER, NUNOTA, fatura parcial, CODPROD, REFERENCIA, QTDNEG, QTDESTOQUE, valor de venda do item, PENDENTE e STATUS.
Se a ordem das colunas mudar no relatório, `scripts/gerar_dados.py` e `index.html` precisam ser ajustados juntos.

Arquivos no layout antigo (10 colunas, sem estoque e status) continuam guardados em `dados/xlsx/`, mas são ignorados pelo painel.

## Configuração (uma única vez)

### GitHub
1. Crie o repositório e envie todo o conteúdo desta pasta para a branch `main` (incluindo a pasta oculta `.github`).
2. Settings → Pages → *Source*: **GitHub Actions**.
3. Aba Actions → *Publicar painel* → *Run workflow* (primeira publicação).
4. Gere o token: Settings da sua conta → Developer settings → Personal access tokens → **Fine-grained tokens** → *Generate new token*.
   - *Repository access*: **Only select repositories** → o repositório do painel.
   - *Permissions* → *Repository permissions* → **Contents: Read and write**.
   - Anote a data de validade: quando o token vence, a alimentação para.

### Google (logado na conta Gmail que recebe o relatório)
1. Abra script.google.com → *Novo projeto* → cole o conteúdo de `apps-script/Codigo.gs`.
2. Configurações do projeto (engrenagem) → *Propriedades do script* → adicione:
   - `GITHUB_TOKEN`: o token gerado acima.
   - `GITHUB_REPO`: `dono/repositorio` (ex.: `ghpc/painel-separacao`).
   - `FILTRO_REMETENTE`: e-mail usado pelo ERP no envio. **Recomendado**: sem ele, qualquer pessoa que mande um XLSX para a conta alimenta o painel.
   - `FILTRO_ANEXO` (opcional, padrão `SEPARACAO`): trecho do nome do anexo.
3. Execute a função `importarSeparacao` uma vez e autorize o acesso ao Gmail. Confira no registro de execução os arquivos enviados.
4. Execute a função `criarGatilho` uma vez. A importação passa a rodar de hora em hora.

## Uso do dia a dia

- **Carga manual:** envie um XLSX para `dados/xlsx/` com o nome `AAAA-MM-DD_SEPARACAO.xlsx`; o painel é atualizado sozinho.
- **Abrir um dia específico:** `.../index.html?dia=2026-10-08`.
- **Falhas:** se o GitHub recusar o envio (token vencido, por exemplo), o Google avisa por e-mail e o script tenta de novo na hora seguinte. O painel também mostra um alerta quando o último arquivo tem 4 dias ou mais.
- **E-mails antigos:** o script olha os últimos 10 dias. Para importar um período maior, aumente `DIAS_BUSCA` no código e execute uma vez.

## Atenção: privacidade

Um site do GitHub Pages é acessível por qualquer pessoa que tenha o endereço, mesmo com repositório privado (restrição de acesso ao site só existe no plano Enterprise Cloud). Em repositório público, os XLSX do histórico também ficam visíveis. Confirme as regras do plano de vocês antes de publicar dados comerciais.

## Estrutura

    index.html                       painel
    dados/xlsx/                      histórico de arquivos recebidos
    apps-script/Codigo.gs            Gmail -> dados/xlsx (roda no Google)
    scripts/gerar_dados.py           dados/xlsx -> JSON do painel (roda na publicação)
    .github/workflows/atualizar.yml  publicação automática
