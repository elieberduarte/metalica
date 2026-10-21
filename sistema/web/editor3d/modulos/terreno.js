// A obra no terreno no editor 3D (21/10, o usuário no PRATI CD: "no modo editar não consegui encontrar a camada do
// terreno"): a mesma imagem do chão do modo ver (web/visor3d/terreno.js, a amarração e a imagem guardadas no projeto),
// numa linha "Terreno (imagem)" no alto do painel Camadas. Só ver: a posição, o norte, a altura e a transparência se
// ajustam no modo ver (botão Terreno). O editor desenha em metros: o terreno vai com a ESCALA da cena.

import * as THREE from 'three';
import { ESCALA } from '../nucleo/cena.js';

/** O "visor" que o terreno.js espera, por cima da cena do editor (mm do projeto, sem origem deslocada). */
function adaptador(ed) {
  let malhas = [], contadas = -1, quadros = 0;
  return {
    get cena() { return ed.cena.cena; },
    cabecalho: { origem: [0, 0, 0] },
    get renderer() { return ed.cena.renderer; },
    get camera() { return ed.camera.ativa; },
    pedirQuadro: () => ed.cena.pedirQuadro(),
    // a caixa do modelo em mm (o pé da obra, na altura automática)
    get _caixaModelo() {
      const cx = new THREE.Box3().setFromObject(ed.cena.raiz);
      return cx.isEmpty() ? new THREE.Box3(new THREE.Vector3(), new THREE.Vector3())
        : new THREE.Box3(cx.min.clone().divideScalar(ESCALA), cx.max.clone().divideScalar(ESCALA));
    },
    // as malhas da obra (marcam o estêncil: a transparência só sobre elas); refeitas quando o modelo ganha ou perde malhas
    get malhas() {
      if (contadas >= 0 && ++quadros % 60) return malhas;  // a recontagem a cada 60 quadros (o modelo grande tem milhares de nós)
      let n = 0;
      ed.cena.raiz.traverse(o => { if (o.isMesh) n++; });
      if (n !== contadas) {
        contadas = n;
        malhas = [];
        ed.cena.raiz.traverse(o => { if (o.isMesh && o.material && !Array.isArray(o.material)) malhas.push({ malha: o }); });
      }
      return malhas;
    },
  };
}

/** Lê o terreno do projeto e o põe no chão do editor; `ed._terreno` fica com ele (null sem local ou sem imagem). */
export async function carregarTerrenoNoEditor(ed) {
  ed._terreno = null;
  if (!ed.projeto) return null;
  try {
    const { Terreno } = await import('../../visor3d/terreno.js');
    const t = new Terreno(adaptador(ed), ed.projeto, { escala: ESCALA, chaveLigado: 'editor3d.terreno', situacao: () => {},
      palco: ed.el.canvas.parentElement });
    if (!(await t.carregar()) || !t.malha) return null;
    ed._terreno = t;
    if (typeof ed._agendarPaineis === 'function') ed._agendarPaineis('camadas');
    return t;
  } catch (e) {
    return null;                                     // sem o terreno (o programa instalado: a rota não existe), o resto igual
  }
}
