# Auditoria técnica e funcional — IdeiaTech

**Data:** 22/10/2026  
**Objetivo:** avaliar a prontidão do MVP para apresentação amanhã à tarde, cobrindo fluxos, estrutura, interface, funcionamento e riscos.

## Resumo executivo

O sistema tem uma base funcional coerente para uma demonstração local: autenticação com sessão, proteção CSRF, catálogo, carrinho/pedidos, solicitações de assistência, orçamentos e painel empresarial. Os 20 testes automatizados existentes passaram e uma inspeção HTTP percorreu as 25 páginas e os recursos locais.

**Não encontrei falha crítica reproduzível nesta auditoria.** Há, porém, um risco de credibilidade importante para o público técnico: a funcionalidade apresentada como “IdeiaAI” não chama um modelo de IA. Também faltam testes automatizados para a maior parte dos fluxos de assistência, autenticação e orçamento. O projeto está documentado como execução local de desenvolvimento; a prontidão de implantação em produção não foi demonstrada.

## Achados por gravidade

### Alta — apresentação de análise fixa como “IdeiaAI”

**Evidência:** `POST /api/orcamento/analisar` em `BackEnd/app.py` seleciona texto, preço e prazo de dicionários fixos a partir da categoria. Não consulta `BackEnd/ia_prompt.py` nem um provedor de modelo. O texto da experiência apresenta a análise como realizada pela IdeiaAI.

**Impacto:** um espectador com conhecimento técnico pode perguntar sobre modelo, contexto, inferência e fontes; a implementação atual não sustenta essa narrativa. As faixas também são descritas como referências públicas compiladas em 2026 sem fonte rastreável no produto.

**Ação antes da apresentação:** ou integrar de verdade o modelo e mostrar claramente limites/fonte, ou ajustar o rótulo e a fala para “estimativa orientativa por categoria”/“triagem preliminar”. Não apresentar valores e prazos como pesquisa validada; explicar que são referências ilustrativas e confirmar com a assistência.

### Média — cobertura de testes estreita diante dos fluxos disponíveis

**Evidência:** os 20 testes existentes concentram-se em pedidos/estoque e dados empresariais. Não há cobertura automatizada aparente equivalente para cadastro, login, recuperação de senha, perfil/endereço, frete, solicitação de atendimento/coleta, orçamento, decisão do cliente, ordens de serviço, transições de status ou validação visual responsiva.

**Impacto:** regressões nesses percursos podem passar despercebidas, mesmo com a suíte atual verde.

**Ação de maior retorno:** priorizar um roteiro manual de demonstração de ponta a ponta e conferir dados/contas previamente. Depois da apresentação, expandir a suíte por fluxo crítico, especialmente orçamento e atendimento.

### Média — dependências externas podem prejudicar a demo

**Evidência:** a consulta de CEP de coleta depende do ViaCEP no navegador; páginas também carregam fontes do Google Fonts. A auditoria verificou os recursos locais, mas não validou disponibilidade dessas dependências externas.

**Impacto:** uma rede instável pode atrasar preenchimento de endereço e alterar a aparência tipográfica; não deve impedir os fluxos que permitem preenchimento manual.

**Ação:** testar no local e na rede que serão usados. Deixar endereço preenchido ou CEP conhecido pronto e manter alternativa de digitação manual. Verificar a tipografia após carregar a página.

### Baixa — validação de e-mail é permissiva em alguns formulários

**Evidência:** validações do servidor aceitam presença de `@` como verificação básica em partes do cadastro.

**Impacto:** entradas malformadas podem ser cadastradas e causar falhas futuras em comunicação/recuperação. Não bloqueia uma demonstração com dados corretos.

**Ação:** aplicar validação de formato consistente no servidor e confirmar o endereço quando houver fluxo de e-mail real.

### Baixa — ambiente de produção não foi validado

**Evidência:** `COMO_RODAR.md` define a execução atual como desenvolvimento local e descreve configurações necessárias de produção (HTTPS, chave persistente, SMTP e `APP_ENV=production`). Não foi apresentada configuração de deploy nem ensaio nesse ambiente.

**Impacto:** não é possível concluir que a aplicação está pronta para exposição pública ou uso real com clientes. A demonstração local pode seguir, desde que preparada como tal.

**Ação:** para amanhã, executar localmente, usar conta/dados de demonstração e evitar prometer operação em produção. Planejar ensaio de implantação separado.

## Verificações executadas

- Suíte existente: **20 testes passaram** (`unittest discover -s BackEnd/tests`).
- A execução inicial usando o diretório temporário padrão do sandbox falhou por permissão de escrita no `%TEMP%`; ao direcionar `TEMP` e `TMP` para `.test-tmp` dentro do projeto, a mesma suíte concluiu com sucesso. Isso é uma limitação do ambiente de execução, não uma falha dos testes/produto.
- Smoke test HTTP das **25 páginas HTML**: páginas públicas retornaram 200; páginas que exigem sessão redirecionaram anonimamente para autenticação (302), como esperado. Recursos locais em `Style`, `Script` e `Assets` retornaram 200.
- Inspeção estática das rotas, formulários, scripts, segurança de sessão/CSRF e principais tabelas/relacionamentos do SQLite.
- Inspeção do comportamento de análise de orçamento e identificação de chamadas a serviços externos.

## Limites da auditoria

Esta rodada não fez ensaio visual em múltiplos navegadores/tamanhos de tela, teste de carga, pentest, revisão completa de acessibilidade, teste de envio de e-mail/SMTP nem validação de deploy. O smoke test confirmou disponibilidade HTTP das páginas e recursos locais, mas não exercitou cada formulário e transição como uma pessoa navegando na interface. Portanto, “20 testes verdes” não equivale a cobertura integral do sistema.

## Roteiro recomendado para a apresentação

1. Entrar com uma conta empresarial preparada e mostrar o painel e os indicadores.
2. Abrir uma solicitação de assistência como cliente, mostrar a análise preliminar e o envio.
3. Alternar para a empresa, demonstrar resposta/orçamento e avanço do atendimento.
4. Voltar ao cliente para acompanhar e aprovar/recusar, conforme os dados de demonstração.
5. Mostrar catálogo, carrinho e pedido somente se estoque e conta estiverem preparados.
6. Usar dados fictícios, conferir as duas sessões/contas antes do evento e manter o servidor local iniciado.

**Recomendação para o MVP:** adequado para demo local guiada após ensaio dos passos escolhidos. Antes de apresentar, alinhar a narrativa da IdeiaAI com o comportamento real e validar a sequência usando as contas e dados exatos que serão mostrados.
