# Teste seguro de limite de consultas

`safe_rate_limit_demo.py` testa inteiramente em memoria como um cliente deve
se comportar diante de cotas e respostas de bloqueio. Ele nao envia consultas
ao Sharkscope nem tenta contornar controles de acesso ou limites de uso.

Execute com:

```bash
python3 safe_rate_limit_demo.py
```

Para uma integracao real, use apenas a API/documentacao oficial e uma conta ou
permissao que autorize o volume de consultas. Mantenha o limite configurado no
cliente, trate `401`, `403` e `429` como parada imediata e registre a cota
utilizada para evitar excede-la por acidente.
