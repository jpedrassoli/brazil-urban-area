"""Testes rápidos, sem Earth Engine (só lógica local). Rodar: python -m unittest discover -s tests -v"""
import copy
import unittest

import numpy as np
import pandas as pd

from mb_urban import classify, config, registry, thresholds

CFG = config.load(config.EXAMPLE_CONFIG)


class JanelasDeAmostras(unittest.TestCase):
    def test_janela_por_ano(self):
        cfg = copy.deepcopy(CFG)
        cfg["samples"]["recent_window"] = {"start": 2017, "end": 2025, "used_from": 2021}
        esperado = {1985: "1985_to_2020", 1992: "1985_to_2020", 1993: "1993_to_2020", 2000: "1993_to_2020",
                    2001: "2001_to_2020", 2008: "2001_to_2020", 2009: "2009_to_2020", 2020: "2009_to_2020",
                    2021: "2017_to_2025", 2025: "2017_to_2025"}
        for ano, janela in esperado.items():
            self.assertEqual(classify.window_for_year(ano, cfg), janela, ano)

    def test_faixas_agrupam_anos_seguidos(self):
        f = registry._faixas({1985: "a", 1986: "a", 1987: "b", 1988: "a"})
        self.assertEqual([x["anos"] for x in f], ["1985-1986", "1987-1987", "1988-1988"])


class Fallback(unittest.TestCase):
    def test_desligado_por_padrao(self):
        self.assertFalse(classify.fallback_cfg(CFG)["enabled"])

    def test_ligar_preserva_demais_padroes(self):
        cfg = copy.deepcopy(CFG)
        cfg["classification"]["sample_fallback"] = {"enabled": True}
        f = classify.fallback_cfg(cfg)
        self.assertTrue(f["enabled"])
        self.assertEqual(f["min_per_class"], 50)
        self.assertEqual(f["rings_km"], [50, 100, 200, 400, 800])


class Limiares(unittest.TestCase):
    def _df(self, urb, nao, carta="X", ano=2000):
        y = np.r_[np.ones(len(urb)), np.zeros(len(nao))]
        return pd.DataFrame({"classification": np.r_[urb, nao], "value": y, "year": ano, "carta": carta})

    def test_youden_separa_classes(self):
        d = self._df([80, 85, 90, 95], [5, 10, 15, 20])
        r = thresholds.by_year(d, CFG).iloc[0]
        self.assertGreater(r["threshold"], 20)
        self.assertLessEqual(r["threshold"], 80)
        self.assertEqual(r["sensitivity"], 1.0)
        self.assertEqual(r["specificity"], 1.0)

    def test_sem_urbano_usa_vazio_e_media_nacional(self):
        d = pd.concat([self._df([80, 90], [5, 10], carta="A"), self._df([], [5, 10], carta="B")])
        y = thresholds.by_year(d, CFG)
        t = thresholds.by_carta(y, ["A", "B"], CFG)
        b = t[t.carta == "B"].iloc[0]
        self.assertFalse(np.isnan(b["threshold"]))        # preenchida com a mediana nacional
        self.assertEqual(int(b["n_years_available"]), 0)


class Rodadas(unittest.TestCase):
    def test_base_nao_muda_nada(self):
        self.assertEqual(config.apply_run(CFG, None)["classification"]["folder"], CFG["classification"]["folder"])
        self.assertEqual(config.apply_run(CFG, "base")["postprocess"]["folder"], CFG["postprocess"]["folder"])

    def test_rodada_usa_pastas_proprias_sem_alterar_a_original(self):
        r = config.apply_run(CFG, "fallback1")
        self.assertTrue(r["classification"]["folder"].endswith("__fallback1"))
        self.assertTrue(r["postprocess"]["folder"].endswith("__fallback1"))
        self.assertFalse(CFG["classification"]["folder"].endswith("__fallback1"))


class Registro(unittest.TestCase):
    def test_ficha_sem_earth_engine(self):
        rec = registry.provenance("SF-23-Y-C", CFG, with_ee=False)
        self.assertEqual(rec["carta"], "SF-23-Y-C")
        self.assertIn("pipeline_texto", rec)
        self.assertEqual(rec["classificacao"]["rotulo_das_bandas"], "by_class")


if __name__ == "__main__":
    unittest.main()
