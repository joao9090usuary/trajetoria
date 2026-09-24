# Registro de verificação — 24/09/2026

## Resultado

A compilação C++17 para WebAssembly/WASI foi concluída com Zig 0.15.2. A suíte analítica C++ passou via Node.js 24. Os **31 testes Python passaram**, cobrindo integração, motores, recuperação e preparação para publicação. A sintaxe do JavaScript também foi verificada.

```sh
python build.py --wasm
python run-tests.py
node --check trajetoria/static/app.js
python -m analises.revisao_numerica
```

O ambiente local utilizou Windows, Python 3.14 e Node.js 24. A compilação nativa por CMake é disponibilizada para reprodução; este registro não afirma execução local da suíte em Linux ou macOS.

## Erros identificados e correções

| Problema | Correção e evidência |
|---|---|
| Descontinuidade de empuxo prejudicava o resultado no fim da queima | Avaliação pela esquerda no último estágio de integração da queima; amostra exportada com empuxo zero. Referência analítica aprovada |
| Tentativas do integrador consumiam massa na curva | Avaliação pura de massa por integral acumulada da curva; teste de independência da ordem de consulta |
| Estimativa de erro podia ser ignorada após poucas subdivisões | Passos rejeitados até satisfazer a tolerância; falha explícita se a integração não puder avançar |
| Abertura alterava estados durante avaliações intermediárias | Estados atualizados em eventos aceitos; fração de abertura preservada em cada amostra |
| Entrada `time_step=0` podia bloquear o núcleo | Validação no C++ antes de integrar; teste de rejeição aprovado |
| Booleanos aceitos como massas | Validação estrita de tipos na aplicação Python |
| Curva ausente no JSON exportado | Pontos incluídos na configuração; teste de exportação e nova simulação com resultado idêntico |
| Teste de finitude tentava tratar estados textuais como números | Teste atualizado para verificar números e estados separadamente |
| Alguns campos da interface não chegavam aos cálculos | Resolução correta de nomes e identificadores dos campos |
| Importador ordenava dados e podia misturar motores | Importação validada no servidor, sem ordenação silenciosa, com motores separados |
| Respostas HTTP maiores podiam ficar incompletas no ambiente local | Escrita em blocos limitados e fechamento explícito da conexão; fluxo HTTP de curva aprovado |
| Gráficos de arrasto e aceleração estavam sem séries | Séries vinculadas à telemetria; aceleração assinada identificada como variação da rapidez |

## Referências numéricas

A suíte C++ verifica movimento balístico, massa variável, fim da queima, apogeu, contato com o solo, convergência, decolagem atrasada e invariantes. Também verifica interpolação e impulso de uma curva triangular e equilíbrio de forças na velocidade terminal sob condições controladas.

Para o caso sintético de queima rápida no vácuo — massa seca de 0,05 kg, propelente de 0,5 kg, empuxo de 100 N, queima de 0,1 s e passo máximo de 0,1 s:

| Grandeza | Referência analítica | Resultado corrigido |
|---|---:|---:|
| Velocidade vertical no fim da queima | 46,97724045596741 m/s | 46,97724045596806 m/s |
| Altitude no fim da queima | 1,4713876954403262 m | 1,4713876954403171 m |

As casas decimais são apresentadas para permitir a comparação computacional, não como resolução experimental. O script de análise gera um relatório local em `output/`, excluído do Git.

## Recuperação e integração

Os testes incluem gatilho no apogeu, atraso de ejeção, duração de abertura, gatilho temporal, cruzamento de altitude na descida, limiar acima do apogeu, ausência de ejeção no apoio, descida com paraquedas, finitude do histórico e convergência com curva e recuperação combinadas.

Os testes de API cobrem identidade com o núcleo, importação de motor, normalização de configuração, comparação de medições, rejeição de entradas inválidas, origem e Host externos, tipo de conteúdo, caminhos de exportação e acesso indevido a arquivos.

## Preparação para publicação

A interface foi exercitada no navegador com alteração da massa seca para 0,45 kg e recuperação no apogeu. O estudo refletiu a massa informada; a memória de cálculo exibiu gatilho, ejeção, abertura completa e contato com o solo. A página de cálculos foi inspecionada visualmente, mantendo o tema institucional claro. Esta revisão não executou uma matriz completa de navegadores ou testes de acessibilidade.

O verificador inspeciona o conteúdo preparado no índice Git. Seus testes demonstram aceitação de documentação pública, rejeição de `.env` e detecção de um token sintético sem exibi-lo. Também verificam que corrigir apenas o arquivo no disco não esconde um segredo ainda preparado no índice.

Não foram fornecidos dados reais de voo nesta revisão. Os resultados não constituem validação experimental, auditoria de segurança completa ou certificação de precisão de 99,9%.
