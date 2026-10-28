"""
Entrega 3 — tabela de simbolos e verificacao de tipos.

Escopos: ARVORE de objetos Escopo, cada um com ponteiro para o pai. Todos ficam
guardados em `escopos` (na ordem em que abrem) mesmo depois de fechados, porque
o --tabela imprime todos e a Entrega 4 vai precisar percorre-los para dar uma
posicao de memoria a cada nome.

Duas passadas:
  1. coletar(): so as assinaturas das funcoes (permite chamar antes de declarar)
  2. as funcoes, uma a uma, abrindo escopos conforme desce nos blocos.
"""
from mplc.erros import ErroMPL

NUM = ('inteiro', 'real')


# ------------------------------------------------------------------ regras de tipo

def cabe(destino, origem):
    """A unica conversao implicita da MPL: inteiro -> real (LINGUAGEM.md 3.1)."""
    return destino == origem or (destino == 'real' and origem == 'inteiro')


def tipo_binario(op, a, b):
    """Tipo do resultado de `a op b`, ou None se a combinacao e erro (secao 3.2)."""
    if op == '+' and a == 'texto' and b == 'texto':
        return 'texto'
    if op in ('+', '-', '*', '/'):
        if a in NUM and b in NUM:
            return 'inteiro' if (a == 'inteiro' and b == 'inteiro') else 'real'
        return None
    if op == '%':
        return 'inteiro' if (a == 'inteiro' and b == 'inteiro') else None
    if op in ('==', '!='):
        return 'logico' if (a == b or (a in NUM and b in NUM)) else None
    if op in ('<', '<=', '>', '>='):
        return 'logico' if (a in NUM and b in NUM) else None
    if op in ('e', 'ou'):
        return 'logico' if (a == 'logico' and b == 'logico') else None
    return None


def tipo_no(no):
    """'binario +' -> 'binario'; 'literal texto "a b"' -> 'literal'."""
    return no.rotulo.split(' ', 1)[0]


def garante_retorno(no):
    """So olha a ESTRUTURA, nunca o valor da condicao."""
    t = tipo_no(no)
    if t == 'retorne':
        return True
    if t == 'bloco':
        return any(garante_retorno(c) for c in no.filhos)
    if t == 'se':
        # sem senao nunca garante; com senao, os dois lados tem que garantir
        return len(no.filhos) == 3 and garante_retorno(no.filhos[1]) and garante_retorno(no.filhos[2])
    return False   # enquanto, escreva, atribuicao... nunca garantem


# ------------------------------------------------------------------ tabela

class Simbolo:
    def __init__(self, nome, categoria, tipo, linha, params=None):
        self.nome = nome
        self.categoria = categoria      # 'funcao' | 'parametro' | 'variavel'
        self.tipo = tipo                # tipo da variavel, ou tipo de retorno da funcao
        self.linha = linha
        self.params = params or []      # so para funcao: lista dos tipos dos parametros


class Escopo:
    def __init__(self, id, descricao, pai):
        self.id = id
        self.descricao = descricao
        self.pai = pai
        self.simbolos = {}              # dict preserva a ordem de declaracao

    def declarar(self, simbolo):
        if simbolo.nome in self.simbolos:
            return False                # redeclaracao no MESMO escopo
        self.simbolos[simbolo.nome] = simbolo
        return True

    def buscar(self, nome):
        """Sobe a cadeia de pais: o primeiro que achar e o mais interno (sombreamento)."""
        e = self
        while e is not None:
            if nome in e.simbolos:
                return e.simbolos[nome]
            e = e.pai
        return None


# ------------------------------------------------------------------ analisador

class Analisador:
    def __init__(self):
        self.escopos = []
        self.global_ = self.abrir('global', None)    # escopo 0
        self.atual = self.global_
        self.funcao_atual = None

    def abrir(self, descricao, pai):
        e = Escopo(len(self.escopos), descricao, pai)
        self.escopos.append(e)
        return e

    def erro(self, no, msg):
        raise ErroMPL('semantico', no.linha, no.coluna, msg)

    # -------------------------------------------------------------- passada 1

    def coletar(self, programa):
        for f in programa.filhos:
            nome = f.extra['nome']
            params = f.filhos[0].filhos
            for p in params:
                if p.extra['tipo'] == 'vazio':
                    self.erro(p, f"parametro '{p.extra['nome']}' nao pode ser do tipo vazio")
            if nome in self.global_.simbolos:
                self.erro(f, f"funcao '{nome}' ja foi declarada")
            self.global_.declarar(Simbolo(nome, 'funcao', f.extra['tipo'], f.linha,
                                          [p.extra['tipo'] for p in params]))
        principal = self.global_.simbolos.get('principal')
        if principal is None:
            self.erro(programa, "falta a funcao 'principal'")
        if principal.params or principal.tipo != 'vazio':
            f = next(f for f in programa.filhos if f.extra['nome'] == 'principal')
            self.erro(f, "'principal' tem que ser 'funcao vazio principal()'")

    # -------------------------------------------------------------- passada 2

    def programa(self, programa):
        self.coletar(programa)
        for f in programa.filhos:
            self.funcao(f)

    def funcao(self, f):
        nome = f.extra['nome']
        sim = self.global_.simbolos[nome]
        self.funcao_atual = sim
        esc = self.abrir(f'funcao {nome}', self.global_)     # 1o escopo: parametros
        self.atual = esc
        for p in f.filhos[0].filhos:
            novo = Simbolo(p.extra['nome'], 'parametro', p.extra['tipo'], p.linha)
            if not esc.declarar(novo):
                self.erro(p, f"parametro '{novo.nome}' repetido")
        corpo = f.filhos[1]
        self.bloco(corpo)                                    # 2o escopo: o bloco
        if sim.tipo != 'vazio' and not garante_retorno(corpo):
            self.erro(f, f"a funcao '{nome}' nao retorna em todos os caminhos")
        self.atual = self.global_
        self.funcao_atual = None

    def bloco(self, no):
        esc = self.abrir('bloco', self.atual)
        self.atual = esc
        for c in no.filhos:
            self.comando(c)
        self.atual = esc.pai

    # -------------------------------------------------------------- comandos

    def comando(self, c):
        t = tipo_no(c)
        if t == 'bloco':
            self.bloco(c)
        elif t == 'declaracao':
            self.declaracao(c)
        elif t == 'atribuicao':
            self.atribuicao(c)
        elif t in ('se', 'enquanto'):
            cond = self.expr(c.filhos[0])
            if cond != 'logico':
                self.erro(c, f"a condicao do '{t}' tem que ser logico, mas e {cond}")
            for corpo in c.filhos[1:]:
                self.bloco(corpo)
        elif t == 'escreva':
            self.expr(c.filhos[0])
        elif t == 'retorne':
            self.retorne(c)
        elif t == 'chamada':
            self.chamada(c, permite_vazio=True)

    def declaracao(self, c):
        nome, tipo = c.extra['nome'], c.extra['tipo']
        if tipo == 'vazio':
            self.erro(c, f"variavel '{nome}' nao pode ser do tipo vazio")
        if c.filhos:
            # a expressao inicial e vista ANTES de o nome existir: `inteiro x = x + 1;` falha
            t = self.expr(c.filhos[0])
            if not cabe(tipo, t):
                self.erro(c, f"nao da para guardar {t} em '{nome}' ({tipo})")
        if not self.atual.declarar(Simbolo(nome, 'variavel', tipo, c.linha)):
            self.erro(c, f"'{nome}' ja foi declarado neste escopo")

    def atribuicao(self, c):
        nome = c.extra['nome']
        sim = self.atual.buscar(nome)
        if sim is None or sim.categoria == 'funcao':
            self.erro(c, f"variavel '{nome}' nao foi declarada")
        t = self.expr(c.filhos[0])
        if not cabe(sim.tipo, t):
            self.erro(c, f"nao da para atribuir {t} a '{nome}' ({sim.tipo})")

    def retorne(self, c):
        esperado = self.funcao_atual.tipo
        if c.filhos:
            if esperado == 'vazio':
                self.erro(c, 'funcao vazio nao retorna valor')
            t = self.expr(c.filhos[0])
            if not cabe(esperado, t):
                self.erro(c, f'retorno {t} em funcao {esperado}')
        elif esperado != 'vazio':
            self.erro(c, f'falta o valor do retorne (funcao {esperado})')

    # ------------------------------------------------------------- expressoes

    def expr(self, no):
        """Devolve o tipo da expressao (nunca 'vazio')."""
        t = tipo_no(no)
        if t == 'literal':
            return no.extra['tipo']
        if t == 'variavel':
            sim = self.atual.buscar(no.extra['nome'])
            if sim is None or sim.categoria == 'funcao':
                self.erro(no, f"variavel '{no.extra['nome']}' nao foi declarada")
            return sim.tipo
        if t == 'chamada':
            return self.chamada(no, permite_vazio=False)
        if t == 'unario':
            op = no.extra['op']
            tipo = self.expr(no.filhos[0])
            if op == 'nao' and tipo == 'logico':
                return 'logico'
            if op == '-' and tipo in NUM:
                return tipo
            self.erro(no, f"operador '{op}' nao se aplica a {tipo}")
        if t == 'binario':
            op = no.extra['op']
            a = self.expr(no.filhos[0])
            b = self.expr(no.filhos[1])
            r = tipo_binario(op, a, b)
            if r is None:
                self.erro(no, f"operador '{op}' nao se aplica a {a} e {b}")
            return r
        self.erro(no, 'expressao desconhecida')

    def chamada(self, no, permite_vazio):
        nome = no.extra['nome']
        sim = self.global_.simbolos.get(nome)       # chamadas so olham o global
        if sim is None or sim.categoria != 'funcao':
            self.erro(no, f"funcao '{nome}' nao existe")
        if len(no.filhos) != len(sim.params):
            self.erro(no, f"'{nome}' espera {len(sim.params)} argumento(s), recebeu {len(no.filhos)}")
        for arg, esperado in zip(no.filhos, sim.params):
            t = self.expr(arg)
            if not cabe(esperado, t):
                self.erro(no, f"argumento {t} onde '{nome}' espera {esperado}")
        if sim.tipo == 'vazio' and not permite_vazio:
            self.erro(no, f"'{nome}' e vazio e nao pode ser usada numa expressao")
        return sim.tipo


# ------------------------------------------------------------------ interface

def analisar(arvore):
    """Recebe a raiz da arvore. Devolve a lista de escopos; levanta ErroMPL no 1o erro."""
    a = Analisador()
    a.programa(arvore)
    return a.escopos


def despejar(escopos):
    """Linhas do --tabela, no formato de CONTRATOS.md secao 4."""
    saida = []
    for e in escopos:
        if e.pai is None:
            saida.append(f'escopo {e.id} {e.descricao}')
        else:
            saida.append(f'escopo {e.id} {e.descricao} pai {e.pai.id}')
        for s in e.simbolos.values():
            tipo = f"{s.tipo}({','.join(s.params)})" if s.categoria == 'funcao' else s.tipo
            saida.append(f'  {s.nome}|{s.categoria}|{tipo}|{s.linha}')
    return saida
