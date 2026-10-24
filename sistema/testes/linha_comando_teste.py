# -*- coding: utf-8 -*-
"""Os verificadores do CAD 2D escritos antes da linha de comando (24/10) abriam as ferramentas pela letra solta (L, M,
O = Copiar…). Com a linha de comando, a letra vai para a caixa e o comando roda com Enter ou espaço, pelos atalhos do
AutoCAD. `atalho_na_linha` faz isso pelos testes: quando a letra acabou de cair sozinha na caixa, troca pelo comando de
mesma ferramenta e aperta o espaço — o fluxo de cada teste continua o mesmo."""

#: a letra solta de antes → o comando de agora (web/cad/linha_comando.js ATALHOS)
ANTIGOS = {"l": "L", "p": "PL", "r": "REC", "c": "C", "a": "A", "t": "T", "h": "LE", "d": "D", "j": "MOVERCOTA",
           "s": "S", "g": "H", "m": "M", "o": "CO", "q": "RO", "i": "MI", "e": "E", "b": "X", "w": "J", "n": "EX",
           "k": "F", "f": "O", "u": "DI", "y": "CORTE", "z": "Z"}


#: True enquanto o teste digita um valor que começa com letra ("d500" do círculo): a letra não é atalho
DIGITANDO = [False]


def atalho_na_linha(aba, k):
    """Depois de a tecla `k` descer no desenho: se ela foi sozinha para a linha de comando, executa o comando de antes."""
    if DIGITANDO[0] or len(k) != 1 or k.lower() not in ANTIGOS:
        return False
    v = aba.avaliar("(() => { const c = window.cad; return c && document.activeElement === c.el.medida ? c.el.medida.value : null; })()")
    if v is None or v.lower() != k.lower():
        return False
    novo = ANTIGOS[k.lower()]
    aba.avaliar("(() => { const m = window.cad.el.medida; m.value = %r; m.dispatchEvent(new Event('input')); return 1; })()" % novo)
    aba.cmd("Input.dispatchKeyEvent", type="keyDown", key=" ", code="Space", windowsVirtualKeyCode=32, text=" ", unmodifiedText=" ")
    aba.cmd("Input.dispatchKeyEvent", type="keyUp", key=" ", code="Space", windowsVirtualKeyCode=32)
    aba.drenar(0.1)
    return True


def comando(aba, letras, fim=" "):
    """Digita o comando no desenho (as letras vão para a linha de comando) e executa com o espaço (ou Enter)."""
    for k in letras:
        cod = ord(k.upper())
        aba.cmd("Input.dispatchKeyEvent", type="keyDown", key=k, code="Key" + k.upper(), windowsVirtualKeyCode=cod, text=k, unmodifiedText=k)
        aba.cmd("Input.dispatchKeyEvent", type="keyUp", key=k, code="Key" + k.upper(), windowsVirtualKeyCode=cod)
    if fim == "Enter":
        aba.cmd("Input.dispatchKeyEvent", type="keyDown", key="Enter", code="Enter", windowsVirtualKeyCode=13, text="\r", unmodifiedText="\r")
        aba.cmd("Input.dispatchKeyEvent", type="keyUp", key="Enter", code="Enter", windowsVirtualKeyCode=13)
    else:
        aba.cmd("Input.dispatchKeyEvent", type="keyDown", key=" ", code="Space", windowsVirtualKeyCode=32, text=" ", unmodifiedText=" ")
        aba.cmd("Input.dispatchKeyEvent", type="keyUp", key=" ", code="Space", windowsVirtualKeyCode=32)
    aba.drenar(0.2)
