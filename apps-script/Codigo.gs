/**
 * Painel de Separacao - envia para o GitHub os XLSX que o ERP manda para este Gmail.
 *
 * Configuracao (Configuracoes do projeto > Propriedades do script):
 *   GITHUB_TOKEN      token do GitHub com permissao "Contents: Read and write" SOMENTE no repositorio do painel
 *   GITHUB_REPO       dono/repositorio, ex.: ghpc/painel-separacao
 *   FILTRO_REMETENTE  e-mail usado pelo ERP no envio (recomendado)
 *   FILTRO_ANEXO      trecho do nome do anexo (opcional; padrao SEPARACAO)
 *   GITHUB_BRANCH     opcional; padrao main
 *
 * Depois: execute criarGatilho() uma unica vez. A partir dai importarSeparacao() roda de hora em hora.
 * Cada e-mail e enviado uma unica vez e nenhum arquivo do repositorio e sobrescrito.
 */

var FUSO = 'America/Sao_Paulo';
var DIAS_BUSCA = 10;
var PASTA = 'dados/xlsx/';
var MAX_REGISTRO = 300;

function importarSeparacao() {
  var props = PropertiesService.getScriptProperties();
  var token = props.getProperty('GITHUB_TOKEN');
  var repo = props.getProperty('GITHUB_REPO');
  if (!token || !repo) throw new Error('Configure GITHUB_TOKEN e GITHUB_REPO nas propriedades do script.');
  var branch = props.getProperty('GITHUB_BRANCH') || 'main';
  var filtroAnexo = (props.getProperty('FILTRO_ANEXO') || 'SEPARACAO').toUpperCase();
  var remetente = (props.getProperty('FILTRO_REMETENTE') || '').trim();

  var consulta = 'has:attachment filename:xlsx newer_than:' + DIAS_BUSCA + 'd';
  if (remetente) consulta += ' from:' + remetente;
  else Logger.log('AVISO: FILTRO_REMETENTE vazio - qualquer remetente pode alimentar o painel.');

  var feitos = JSON.parse(props.getProperty('PROCESSADOS') || '[]');
  var enviados = 0;

  // do mais antigo para o mais novo, para os arquivos entrarem em ordem
  var mensagens = [];
  GmailApp.search(consulta, 0, 100).forEach(function (conversa) {
    conversa.getMessages().forEach(function (m) { mensagens.push(m); });
  });
  mensagens.sort(function (a, b) { return a.getDate().getTime() - b.getDate().getTime(); });

  mensagens.forEach(function (msg) {
    var id = msg.getId();
    if (feitos.indexOf(id) >= 0) return;
    if (remetente && msg.getFrom().toLowerCase().indexOf(remetente.toLowerCase()) < 0) return;

    msg.getAttachments().forEach(function (anexo) {
      var nome = anexo.getName() || '';
      if (!/\.xlsx$/i.test(nome) || nome.toUpperCase().indexOf(filtroAnexo) < 0) return;
      var bytes = anexo.getBytes();
      if (bytes.length < 4 || bytes[0] !== 80 || bytes[1] !== 75) {  // todo XLSX comeca com "PK"
        Logger.log('Anexo ignorado (nao e um XLSX valido): ' + nome);
        return;
      }
      // o relatorio traz o dia anterior ao envio
      var vespera = new Date(msg.getDate().getTime() - 24 * 60 * 60 * 1000);
      var dia = Utilities.formatDate(vespera, FUSO, 'yyyy-MM-dd');
      var hora = Utilities.formatDate(msg.getDate(), FUSO, 'HHmmss');
      var caminho = PASTA + dia + '_SEPARACAO.xlsx';
      if (existeNoGitHub_(repo, branch, token, caminho)) {
        caminho = PASTA + dia + '_SEPARACAO_' + hora + '.xlsx';   // reenvio do mesmo dia: guarda os dois
        if (existeNoGitHub_(repo, branch, token, caminho)) return; // este e-mail ja foi enviado antes
      }
      gravarNoGitHub_(repo, branch, token, caminho, bytes);
      Logger.log('Enviado: ' + caminho);
      enviados++;
    });

    feitos.push(id);  // so chega aqui se nenhum envio falhou; em caso de erro tenta de novo na proxima hora
    props.setProperty('PROCESSADOS', JSON.stringify(feitos.slice(-MAX_REGISTRO)));
  });

  Logger.log(enviados + ' arquivo(s) enviado(s) ao GitHub.');
}

function urlGitHub_(repo, caminho) {
  return 'https://api.github.com/repos/' + repo + '/contents/' + caminho.split('/').map(encodeURIComponent).join('/');
}

function cabecalhos_(token) {
  return { Authorization: 'Bearer ' + token, Accept: 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28' };
}

function existeNoGitHub_(repo, branch, token, caminho) {
  var r = UrlFetchApp.fetch(urlGitHub_(repo, caminho) + '?ref=' + encodeURIComponent(branch),
    { method: 'get', headers: cabecalhos_(token), muteHttpExceptions: true });
  var codigo = r.getResponseCode();
  if (codigo === 200) return true;
  if (codigo === 404) return false;
  throw new Error('GitHub recusou a consulta (' + codigo + '). Verifique o token e o nome do repositorio. ' + r.getContentText().slice(0, 200));
}

function gravarNoGitHub_(repo, branch, token, caminho, bytes) {
  var r = UrlFetchApp.fetch(urlGitHub_(repo, caminho), {
    method: 'put',
    headers: cabecalhos_(token),
    contentType: 'application/json',
    payload: JSON.stringify({
      message: 'Separacao: ' + caminho.split('/').pop(),
      content: Utilities.base64Encode(bytes),
      branch: branch
    }),
    muteHttpExceptions: true
  });
  if (r.getResponseCode() !== 201) {
    throw new Error('GitHub recusou o envio de ' + caminho + ' (' + r.getResponseCode() + '): ' + r.getContentText().slice(0, 200));
  }
}

/** Execute uma unica vez: agenda a importacao de hora em hora. */
function criarGatilho() {
  ScriptApp.getProjectTriggers().forEach(function (g) {
    if (g.getHandlerFunction() === 'importarSeparacao') ScriptApp.deleteTrigger(g);
  });
  ScriptApp.newTrigger('importarSeparacao').timeBased().everyHours(1).create();
}
