# Arquitetura e contratos

## Organização

`native/flight.hpp` implementa configuração, avaliação de motor, forças e integração. `native/main.cpp` recebe parâmetros e serializa os resultados. O núcleo não acessa a rede.

`trajetoria/physics.py` valida a configuração e envia um protocolo textual ao processo C++, com limite de 30 segundos. `trajetoria/motors.py` normaliza CSV e ENG. `trajetoria/validation.py` compara amostras e medições. `trajetoria/server.py` expõe a aplicação exclusivamente no endereço de loopback.

O navegador manipula formulários e visualizações; não integra a trajetória. A prévia da curva calcula apenas estatísticas dos pontos para apresentação. Os valores do estudo são produzidos pelo núcleo C++.

## Configuração e resultados

A configuração é um objeto JSON plano. Campos omitidos recebem os padrões de `Config`. Campos desconhecidos são rejeitados; números devem ser finitos e não podem ser booleanos.

| Campo | Unidade ou tipo | Padrão | Limites |
|---|---|---:|---|
| `dry_mass` | kg | 0,35 | 0,01 a 100 |
| `propellant_mass` | kg | 0,08 | 0,001 a 100 |
| `thrust` | N | 12 | 0 a 10.000 |
| `burn_time` | s | 2 | 0,01 a 100 |
| `diameter` | m | 0,05 | 0,01 a 1 |
| `drag_coefficient` | adimensional | 0,55 | 0 a 2 |
| `elevation` | graus acima do horizonte | 85 | 60 a 90 |
| `azimuth` | graus, horário a partir do norte | 30 | 0 a 360 |
| `wind_east`, `wind_north` | m/s | 2; 0,5 | −30 a 30 |
| `air_density` | kg/m³ no solo | 1,225 | 0 a 1,5 |
| `time_step` | s, passo máximo | 0,02 | 0,001 a 0,1 |
| `max_time` | s | 120 | 10 a 1.000 |
| `motor_mode` | texto | `constant` | `constant` ou `curve` |
| `thrust_curve` | pares `[tempo, empuxo]` | lista vazia | 2 a 10.000 pontos no modo curva |
| `recovery_enabled` | booleano | `false` | Ativa a recuperação |
| `recovery_trigger` | texto | `apogee` | `apogee`, `time` ou `altitude` |
| `recovery_delay` | s após o gatilho | 0 | 0 a 60 |
| `recovery_inflation` | s após a ejeção | 1 | 0,01 a 30 |
| `recovery_area` | m², área projetada aberta | 0,3 | 0,001 a 20 |
| `recovery_cd` | adimensional | 1,5 | 0,1 a 3 |
| `recovery_altitude` | m acima do solo | 50 | 0 a 10.000 |
| `recovery_time` | s desde a ignição | 5 | 0 a 180 |

Esses intervalos limitam a entrada computacional; não definem validade física. No modo curva, `thrust` e `burn_time` permanecem na configuração para compatibilidade, mas a propulsão utiliza exclusivamente os pontos. `summary.burn_duration` informa a duração efetivamente usada. O modo constante exige curva vazia.

A saída contém `config`, `status`, `summary`, `events`, `samples` e `model`. `config` inclui os pontos utilizados, permitindo nova execução pelo CLI Python. O modelo registra versão 2.0.0 e tolerâncias numéricas. Nome de arquivo e metadados de catálogo exibidos na importação não são persistidos na configuração; a rastreabilidade experimental da fonte permanece responsabilidade do usuário.

Estados finais: `landed` para contato com o solo, `time_limit` para interrupção no limite de tempo e `no_liftoff` quando o motor não produz decolagem. Não há dinâmica de colisão. Um resultado sem decolagem apresenta a amostra inicial, sem animar toda a queima no apoio.

## Avaliação do motor

O motor é avaliado por funções puras de tempo. A massa não é consumida por efeito colateral de chamadas do integrador, tentativas rejeitadas ou buscas de eventos.

- Empuxo constante: consumo linear de propelente até `burn_time`.
- Curva: interpolação linear; impulso calculado pela integral exata dessa interpolação, por trapézios.
- Consumo na curva: fração de propelente consumida igual a `I(t)/I_total`.
- Término da curva: último instante informado, com empuxo zero.
- Média: impulso total dividido pela duração completa; não utiliza uma convenção de limiar percentual de catálogo.
- A curva CSV admite intervalos intermediários de empuxo zero; eles não encerram definitivamente o motor. O adaptador ENG aplica a convenção RASP de zero apenas na origem e no término.
- A massa seca inclui o sistema de recuperação; a abertura do paraquedas não remove massa.

A decolagem é localizada quando a componente vertical do empuxo supera o peso. O apoio é ideal e não há dinâmica de trilho. Na curva, são considerados os intervalos lineares e os extremos internos da diferença entre empuxo vertical e peso.

## Integração e eventos

O estado é `[east, north, altitude, velocity_east, velocity_north, velocity_up]`. São calculados um passo RK4 inteiro e dois meios passos. A diferença dividida por 15 estima o erro local; a correção de Richardson é aplicada ao estado aceito.

Por componente, a escala é `1e-11 + 1e-12 × max(|estado_inicial|, |estado_final|)`. As tolerâncias absolutas têm a unidade da componente correspondente: metros para posição e metros por segundo para velocidade. Elas são fixas nesta versão e não equivalem a um intervalo de confiança ou erro físico.

Passos são reduzidos até a razão estimada de erro ser no máximo 1. Se a precisão não puder ser atingida, a execução falha explicitamente. Há limites de 300.000 amostras e 1.000.000 de tentativas. O resumo registra passos aceitos, rejeitados e maior razão de erro dos passos candidatos aceitos antes de eventual divisão em eventos.

As fronteiras incluem nós da curva, término da propulsão, gatilho temporal, ejeção, abertura completa e tempo máximo. A retirada instantânea do empuxo constante é tratada com avaliação pela esquerda durante a integração do intervalo de queima e pela direita na amostra de término.

Apogeu, altitude de recuperação e solo são localizados por 45 iterações de bisseção e reintegração dentro do passo. O primeiro apogeu detectado pode acionar a recuperação. Para uma curva não convencional com reaceleração, o gatilho continua associado a esse primeiro evento, enquanto a altitude máxima do resumo considera também as amostras posteriores.

## Recuperação

Movimento, motor e recuperação são estados independentes:

| Subsistema | Valores exportados |
|---|---|
| Movimento | `Supported`, `Ascending`, `Descending`, `Landed` |
| Motor | `Burning`, `Burnout` |
| Recuperação | `None`, `Stowed`, `Armed`, `Inflating`, `FullyOpen` |

Gatilhos:

- `apogee`: primeiro apogeu detectado.
- `time`: instante desde a ignição; se ocorrer antes da decolagem, só é acionado quando há decolagem.
- `altitude`: cruzamento do limiar na descida. Se o apogeu estiver abaixo do limiar, o gatilho ocorre no apogeu.

Após o gatilho, o estado fica `Armed` durante o atraso. Ejeção e início da abertura ocorrem no mesmo instante. A fração cresce linearmente de 0 a 1 durante `recovery_inflation`; depois permanece em 1. Um contato com o solo encerra o voo e impede eventos posteriores.

`effective_cda` representa **somente o acréscimo do paraquedas**. O arrasto total soma esse valor ao produto CdA do corpo. Cada amostra guarda sua própria fração de abertura, evitando recalcular todo o histórico com o estado final.

O modelo não prevê falhas de ejeção, separação de componentes, oscilação, linhas, deformação do velame, rasgo ou cargas estruturais de abertura. A lei de inflação é uma aproximação que requer caracterização experimental.

## API local

Todas as rotas POST exigem `Content-Type: application/json`, `Host` local válido e origem compatível quando informada.

| Rota | Entrada | Saída |
|---|---|---|
| `POST /api/config` | Configuração | Configuração validada com padrões |
| `POST /api/simulate` | Configuração | Estudo completo |
| `POST /api/motor-import` | `{filename, content}` | Lista de motores, pontos, estatísticas e metadados |
| `POST /api/convergence` | `{config}` | Passos e apogeus de h, h/2 e h/4 |
| `POST /api/validate` | `{config, observations}` | Resíduos e métricas |
| `POST /api/export` | `{filename, content}` | URL de download e caminho local |

A comparação de passos exige `time_step >= 0.004`. Exportações aceitam apenas os nomes predefinidos pelo servidor. Conteúdo inválido resulta em erro; o servidor não oferece autenticação para usuários remotos. Consulte [SECURITY.md](../SECURITY.md).

## Evolução recomendada

As próximas etapas de pesquisa são a validação com dados independentes, caracterização de incertezas, rastreabilidade de fontes de motor, suporte a RSE e modelos aerodinâmicos e atmosféricos de maior fidelidade. Ampliar o número de parâmetros não substitui a verificação de cada componente.
