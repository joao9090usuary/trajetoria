# Segurança e privacidade

## Escopo de execução

O Trajetória é uma aplicação local. O servidor escuta somente em `127.0.0.1`, valida o cabeçalho `Host`, rejeita origens HTTP externas e exige JSON nas chamadas de escrita. Os arquivos estáticos são servidos por uma lista explícita; não há navegação livre pelo sistema de arquivos.

O projeto não possui autenticação, isolamento entre usuários ou infraestrutura para hospedagem pública. Não exponha o servidor diretamente à internet. A publicação do código no GitHub não publica a API local como serviço.

## Credenciais e dados particulares

Não é necessário criar `.env` para executar esta versão. O `.gitignore` exclui arquivos de ambiente, chaves privadas, configurações de credenciais, ferramentas locais, binários, registros e diretórios de resultados. Essas exclusões preservam os arquivos locais; não os apagam.

Medições reais, dados pessoais e resultados confidenciais devem ficar em `dados/`, `data/` ou `output/`, que não são versionados. A pasta `exemplos/` deve conter apenas dados sintéticos ou material cuja divulgação esteja autorizada.

Adicionar um nome ao `.gitignore` não remove um arquivo já presente no histórico. Se uma credencial for publicada, revogue-a ou substitua-a no serviço de origem antes de tratar a remoção do histórico.

## Verificação antes de enviar alterações

```sh
git diff --cached --stat
python scripts/verificar_publicacao.py
```

O verificador inspeciona os arquivos preparados no índice do Git, rejeita caminhos fora do escopo e procura padrões comuns de segredos e caminhos pessoais. Ele informa apenas arquivo, linha e categoria, sem imprimir o valor encontrado. Essa análise é preventiva e não substitui revisão humana nem garante a ausência de todos os tipos de dados sensíveis.

## Limites operacionais

- A ponte de cálculo aplica um tempo máximo de execução de 30 segundos.
- O núcleo limita tentativas de integração e quantidade de amostras.
- Importações de motor e requisições de cálculo têm limite de 2 MB.
- Exportações têm limite de 128 MB por requisição e ficam salvas localmente até serem removidas pelo usuário.
- O serviço local não implementa cotas de armazenamento, controle de acesso entre processos locais ou proteção completa contra esgotamento de recursos.
- WASI é uma alternativa de execução, não uma barreira de segurança para módulos não confiáveis.

## Relato de vulnerabilidades

Não publique credenciais, medições privadas ou detalhes exploráveis em uma issue pública. Se o repositório disponibilizar relato privado de vulnerabilidades, utilize esse canal. Caso contrário, solicite ao mantenedor um meio privado de contato antes de compartilhar detalhes sensíveis. Não há prazo de resposta ou programa de recompensa estabelecido.
