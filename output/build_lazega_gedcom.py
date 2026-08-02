# -*- coding: utf-8 -*-
"""Build GEDCOM from Nowy_Korczyn_Lazega_family_research_REORGANIZED_2026-07-17.pdf"""
from pathlib import Path
from datetime import date

OUT = Path(__file__).with_name("Nowy_Korczyn_Lazega_family_REORGANIZED_2026-07-17.ged")

people = {}
families = {}
pid = 0
fid = 0


def add_person(
    name,
    sex="U",
    given=None,
    surname=None,
    birth=None,
    death=None,
    birth_place=None,
    death_place=None,
    notes=None,
    aka=None,
    occupancy=None,
):
    global pid
    pid += 1
    i = f"I{pid}"
    if given is None and surname is None:
        parts = name.strip().split()
        if len(parts) >= 2:
            given = " ".join(parts[:-1])
            surname = parts[-1]
        else:
            given = name
            surname = ""
    people[i] = {
        "name": name,
        "given": given or "",
        "surname": surname or "",
        "sex": sex,
        "birth": birth,
        "death": death,
        "birth_place": birth_place,
        "death_place": death_place,
        "notes": notes or [],
        "aka": aka or [],
        "occupancy": occupancy,
        "famc": None,
        "fams": [],
    }
    return i


def add_family(
    husb=None,
    wife=None,
    children=None,
    marriage=None,
    marriage_place=None,
    notes=None,
):
    global fid
    fid += 1
    f = f"F{fid}"
    ch = children or []
    families[f] = {
        "husb": husb,
        "wife": wife,
        "children": ch,
        "marriage": marriage,
        "marriage_place": marriage_place,
        "notes": notes or [],
    }
    if husb and husb in people:
        people[husb]["fams"].append(f)
    if wife and wife in people:
        people[wife]["fams"].append(f)
    for c in ch:
        if c in people:
            people[c]["famc"] = f
    return f


# ========== A. ROOT: Wulf/Mirla -> Beniamin line ==========
abram_wulf_father = add_person(
    "Abram Łazęga",
    "M",
    given="Abram",
    surname="Łazęga",
    notes=[
        "Named via patronymic Abramowicz of Wulf; generation before Wulf.",
        "STATUS: inferred from patronymic; not independently documented as vital-event subject.",
    ],
)
ojzer = add_person(
    "Ojzer",
    "M",
    given="Ojzer",
    surname="",
    notes=[
        "Father of Mirla (z Ojzerów); surname unknown in 1839 marriage act.",
        "STATUS: named by patronymic only.",
    ],
)

wulf = add_person(
    "Wulf / Wolf Łazęga",
    "M",
    given="Wulf / Wolf",
    surname="Łazęga",
    birth="ABT 1775",
    death="20 MAR 1852",
    death_place="Wiślica, Poland",
    occupancy="Synagogue attendant (szkolnik)",
    aka=["Wulf Abramowicz Łazęga", "Wolf Łazęga"],
    notes=[
        "Wiślica death act 6/1852: age 77; widow Mira; five children (3 sons, 2 daughters) not named individually.",
        "STATUS: ROOT — anchored individual; high-confidence parents of Beniamin, Gitla, Cypa.",
    ],
)
mirla = add_person(
    "Mirla / Mira Łazęga",
    "F",
    given="Mirla / Mira",
    surname="Łazęga",
    aka=["Mirla z Ojzerów", "Mira"],
    notes=[
        "Daughter of Ojzer; adopted surname unknown in 1839 act.",
        "Survived Wolf (1852). STATUS: ROOT.",
    ],
)
add_family(
    husb=abram_wulf_father,
    children=[wulf],
    notes=["Patronymic-only link: Wulf Abramowicz."],
)
add_family(husb=ojzer, children=[mirla], notes=["Patronymic-only link: Mirla z Ojzerów."])

gitla = add_person(
    "Gitla Łazęga",
    "F",
    given="Gitla",
    surname="Łazęga",
    birth="ABT 1810",
    birth_place="Wiślica, Poland",
    notes=[
        "Married Izrael Byk 12 Jun 1829, Wiślica act 4; parents Wulf + Mirla.",
        "STATUS: ROOT collateral — probable sister of Beniamin (high confidence).",
    ],
)
izrael_byk = add_person(
    "Izrael Byk",
    "M",
    given="Izrael",
    surname="Byk",
    birth="ABT 1809",
    occupancy="Merchant",
    notes=["Son of Mosiek Byk and Sora; married Gitla 1829."],
)
mosiek_byk = add_person("Mosiek Byk", "M", given="Mosiek", surname="Byk")
sora_byk = add_person("Sora Byk", "F", given="Sora", surname="Byk")
add_family(husb=mosiek_byk, wife=sora_byk, children=[izrael_byk])

cypa = add_person(
    "Cypa / Cypra Łazęga",
    "F",
    given="Cypa / Cypra",
    surname="Łazęga",
    birth="ABT 1810",
    death="1879",
    aka=["Cypa Luft"],
    notes=[
        "Indexed death 1879 act 27, age 66; parents Wolf and Mirla (JRI-Poland).",
        "1834 birth of daughter Haja Rajzla uses Wolf patronymic.",
        "STATUS: ROOT collateral — high-confidence sister of Beniamin.",
    ],
)
szmul_luft = add_person(
    "Szmul Moszkowicz Luft",
    "M",
    given="Szmul Moszkowicz",
    surname="Luft",
    birth="ABT 1799",
    death="26 FEB 1855",
    death_place="Nowy Korczyn, Poland",
    occupancy="Laborer",
    notes=[
        "Death act 8/1855, age 56; parents Mosiek Luft and Rajzla Blada.",
        "Seven surviving children named in 1855.",
    ],
)
mosiek_luft = add_person("Mosiek Luft", "M", given="Mosiek", surname="Luft")
rajzla_blada = add_person("Rajzla Blada", "F", given="Rajzla", surname="Blada")
add_family(husb=mosiek_luft, wife=rajzla_blada, children=[szmul_luft])

haja_rajzla_luft = add_person(
    "Haja Rajzla Luft",
    "F",
    given="Haja Rajzla",
    surname="Luft",
    birth="5 NOV 1834",
    birth_place="Nowy Korczyn, Poland",
    notes=["Birth act 56/1834; mother Cypa née Łazęga."],
)
mosiek_luft_ch = add_person(
    "Mosiek Luft",
    "M",
    given="Mosiek",
    surname="Luft",
    notes=["Named among Szmul Luft's surviving sons in 1855 death act."],
)
sendla_luft = add_person(
    "Sendla Luft",
    "M",
    given="Sendla",
    surname="Luft",
    notes=["Named among Szmul Luft's surviving sons in 1855."],
)
choryn_luft = add_person(
    "Choryn Luft",
    "M",
    given="Choryn",
    surname="Luft",
    notes=["Named among Szmul Luft's surviving sons in 1855."],
)
dawid_luft = add_person(
    "Dawid Luft",
    "M",
    given="Dawid",
    surname="Luft",
    notes=["Named among Szmul Luft's surviving sons in 1855."],
)
bajla_luft_cypa = add_person(
    "Bajla Luft",
    "F",
    given="Bajla",
    surname="Luft",
    notes=[
        "Named among Szmul Luft's surviving daughters in 1855.",
        "May be same Bajla Rochla Luft mother of Szmul Jankel (merge not forced).",
    ],
)
frajdla_luft = add_person(
    "Frajdla Luft",
    "F",
    given="Frajdla",
    surname="Luft",
    notes=["Named among Szmul Luft's surviving daughters in 1855."],
)

beniamin = add_person(
    "Beniamin Wulfowicz Łazęga",
    "M",
    given="Beniamin Wulfowicz",
    surname="Łazęga",
    birth="ABT 1815",
    death="15 APR 1904",
    death_place="Nowy Korczyn, Poland",
    birth_place="Wiślica, Poland",
    occupancy="Laborer",
    aka=["Beniamin Łazęga", "Biniamin Łazęga", "Benjamin Lazenga"],
    notes=[
        "Death act 15/1904 age 88, parents Wolf and Mirla.",
        "1839 marriage age 20 (~1819). Age drift common.",
        "STATUS: ROOT — founding male of established Nowy Korczyn–Kraków line.",
    ],
)

icek_kozuch = add_person(
    "Icek Kozuch",
    "M",
    given="Icek",
    surname="Kozuch",
    death="BEF 1839",
    notes=["Deceased before daughter Rywka's 1839 marriage."],
)
hencia = add_person(
    "Hencia / Hania (daughter of Icek)",
    "F",
    given="Hencia / Hania",
    surname="",
    aka=["Hania z Icków"],
    notes=[
        "Widow of Icek Kozuch; mother of Rywka; present at 1839 marriage.",
        "Adopted surname unknown.",
    ],
)
icek_hencia_father = add_person(
    "Icek (father of Hencia)",
    "M",
    given="Icek",
    surname="",
    notes=["Patronymic father of Hencia."],
)
add_family(husb=icek_hencia_father, children=[hencia])

rywka = add_person(
    "Rywka Ickowna Kozuch",
    "F",
    given="Rywka Ickowna",
    surname="Kozuch",
    birth="ABT 1820",
    death="BEF 7 FEB 1852",
    death_place="Nowy Korczyn, Poland",
    aka=["Rywka Kozuch"],
    notes=[
        "Married Beniamin 1/13 Jun 1839, Nowy Korczyn act 8.",
        "Proven deceased before Mortka Lejb death act 8 Feb 1852.",
        "STATUS: ROOT — first wife of Beniamin; NOT the same person as Blima.",
    ],
)
add_family(husb=icek_kozuch, wife=hencia, children=[rywka])

mortka_lejb = add_person(
    "Mortka Lejb Łazęga",
    "M",
    given="Mortka Lejb",
    surname="Łazęga",
    birth="ABT 1842",
    death="7 FEB 1852",
    death_place="Nowy Korczyn, Poland",
    notes=[
        "Death act 8/1852 age 10; son of Beniamin and Rywka Kozuch.",
        "STATUS: ROOT.",
    ],
)

abram_kolacz = add_person("Abram Kołacz", "M", given="Abram", surname="Kołacz")
mindla_kolacz = add_person("Mindla Kołacz", "F", given="Mindla", surname="Kołacz")
blima = add_person(
    "Blima Kołacz Łazęga",
    "F",
    given="Blima",
    surname="Kołacz",
    birth="ABT 1820",
    death="6 AUG 1890",
    death_place="Nowy Korczyn, Poland",
    aka=["Blima Lazega", "Blima Kolacz"],
    notes=[
        "Death act 44/1890 age 70; wife of Beniamin; parents Abram and Mindla Kołacz.",
        "STATUS: ROOT — second wife; founding parental couple with Beniamin.",
    ],
)
add_family(husb=abram_kolacz, wife=mindla_kolacz, children=[blima])

haja_rochla = add_person(
    "Haja / Fajga Rochla Łazęga",
    "F",
    given="Haja / Fajga Rochla",
    surname="Łazęga",
    birth="ABT 1856",
    death="5 SEP 1857",
    death_place="Nowy Korczyn, Poland",
    notes=["Death act 39/1857 age 1; daughter of Beniamin and Blima.", "STATUS: ROOT."],
)
rojza_rejla = add_person(
    "Rojza Rejla Łazęga",
    "F",
    given="Rojza Rejla",
    surname="Łazęga",
    birth="ABT 1861",
    notes=[
        "Married Szmul Jankel Miodownik 1887 act 8; age 26; parents Beniamin + Blima.",
        "STATUS: ROOT.",
    ],
)
abram_hersz = add_person(
    "Abram Chersz / Hersz Łazęga",
    "M",
    given="Abram Chersz / Hersz",
    surname="Łazęga",
    birth="ABT 1851",
    birth_place="Nowy Korczyn, Poland",
    occupancy="Glazier / carpenter",
    aka=["Abram Hersz Łazęga", "Abram Chersz Lazenga"],
    notes=[
        "Married Laja Gemzowicz 1879 act 44 age 28.",
        "STATUS: ROOT — bridge generation to Józef Mendel.",
    ],
)

add_family(
    husb=wulf,
    wife=mirla,
    children=[gitla, beniamin, cypa],
    notes=[
        "1852 death: five children not named. Gitla, Beniamin, Cypa linked by parent-pair records.",
        "STATUS: ROOT parental couple.",
    ],
)
add_family(
    husb=izrael_byk,
    wife=gitla,
    marriage="12 JUN 1829",
    marriage_place="Wiślica, Poland",
    notes=["Wiślica marriage act 4/1829."],
)
add_family(
    husb=szmul_luft,
    wife=cypa,
    children=[
        haja_rajzla_luft,
        mosiek_luft_ch,
        sendla_luft,
        choryn_luft,
        dawid_luft,
        bajla_luft_cypa,
        frajdla_luft,
    ],
    notes=["Cypa/Szmul Luft household; children from 1834 birth and 1855 death."],
)
add_family(
    husb=beniamin,
    wife=rywka,
    children=[mortka_lejb],
    marriage="13 JUN 1839",
    marriage_place="Nowy Korczyn, Poland",
    notes=["Marriage act 8/1839 (1/13 Jun OS/NS). Rywka deceased before Feb 1852."],
)
add_family(
    husb=beniamin,
    wife=blima,
    children=[haja_rochla, rojza_rejla, abram_hersz],
    notes=[
        "STATUS: ROOT founding couple of documentary core.",
        "Additional children may exist; only those proved by acts are listed.",
    ],
)

abram_miodownik = add_person("Abram Miodownik", "M", given="Abram", surname="Miodownik")
bajla_rochla_luft = add_person(
    "Bajla Rochla Luft",
    "F",
    given="Bajla Rochla",
    surname="Luft",
    notes=[
        "Mother of Szmul Jankel Miodownik; may be same Bajla Luft daughter of Cypa (unproven merge not forced)."
    ],
)
szmul_jankel = add_person(
    "Szmul Jankel Miodownik",
    "M",
    given="Szmul Jankel",
    surname="Miodownik",
    birth="ABT 1862",
    death="11 JAN 1907",
    death_place="Nowy Korczyn, Poland",
    notes=[
        "Death act 30/1906 (29 Dec OS / 11 Jan NS 1907) age 44.",
        "Married Rojza Rejla 1887.",
    ],
)
add_family(husb=abram_miodownik, wife=bajla_rochla_luft, children=[szmul_jankel])
add_family(
    husb=szmul_jankel,
    wife=rojza_rejla,
    marriage="9 MAR 1887",
    marriage_place="Nowy Korczyn, Poland",
    notes=["Marriage act 8/1887 (25 Feb OS / 9 Mar NS)."],
)

mordka_gemz = add_person(
    "Mordka Gemzowicz",
    "M",
    given="Mordka",
    surname="Gemzowicz",
    birth="ABT 1836",
    occupancy="podenszczyk [uncertain]",
)
chinda = add_person(
    "Chinda / Chindla Blausztajn",
    "F",
    given="Chinda / Chindla",
    surname="Blausztajn",
    birth="ABT 1838",
    aka=["Chinda Blumsztajn"],
)
lejbus_gemz = add_person(
    "Lejbus Gemzowicz",
    "M",
    given="Lejbus",
    surname="Gemzowicz",
    birth="28 APR 1876",
    death="24 JAN 1877",
    birth_place="Nowy Korczyn, Poland",
    death_place="Nowy Korczyn, Poland",
    notes=["Birth act 32/1876; death act 36/1877 age 9 months."],
)
laja = add_person(
    "Laja / Laia Gemzowicz",
    "F",
    given="Laja / Laia",
    surname="Gemzowicz",
    birth="ABT 1860",
    birth_place="Nowy Korczyn, Poland",
    aka=["Laia Gemzowicz"],
    notes=["Married Abram Chersz 1879 age 19. STATUS: ROOT."],
)
chawa_gemz = add_person(
    "Chawa Gemzowicz",
    "F",
    given="Chawa",
    surname="Gemzowicz",
    birth="ABT 1868",
    notes=["Married Berek Koplik 1892 act 22 age 24."],
)
add_family(husb=mordka_gemz, wife=chinda, children=[lejbus_gemz, laja, chawa_gemz])

pinches_koplik = add_person("Pinches Koplik", "M", given="Pinches", surname="Koplik")
sora_rzeznik = add_person("Sora Rzeznik", "F", given="Sora", surname="Rzeznik")
berek_koplik = add_person("Berek Koplik", "M", given="Berek", surname="Koplik", birth="ABT 1862")
add_family(husb=pinches_koplik, wife=sora_rzeznik, children=[berek_koplik])
add_family(
    husb=berek_koplik,
    wife=chawa_gemz,
    marriage="3 NOV 1892",
    marriage_place="Nowy Korczyn, Poland",
    notes=["Marriage act 22/1892 (22 Oct OS / 3 Nov NS)."],
)

szmul_laz = add_person(
    "Szmul Łazęga",
    "M",
    given="Szmul",
    surname="Łazęga",
    birth="17 MAY 1885",
    birth_place="Nowy Korczyn, Poland",
    notes=["Birth act 106/1885 (5/17 May OS/NS). STATUS: ROOT."],
)
jozef_mendel = add_person(
    "Józef / Josek Mendel Łazęga",
    "M",
    given="Józef / Josek Mendel",
    surname="Łazęga",
    birth="16 MAR 1887",
    birth_place="Nowy Korczyn, Poland",
    occupancy="Paper merchant, Rynek Podgórski 2, Kraków",
    aka=["Josek Mendel Lazenga", "Józef Mendel Łazęga", "J. Łazęga"],
    notes=[
        "Birth act 28/1887 (4/16 Mar OS/NS); tree often cites 3 Mar 1887.",
        "Kraków paper business 1920–1931 documented.",
        "STATUS: ROOT — Kraków merchant generation.",
    ],
)
blima_lead = add_person(
    "Blima Łazęga",
    "F",
    given="Blima",
    surname="Łazęga",
    birth="ABT 1896",
    notes=[
        "Secondary-source lead only; no original birth act found.",
        "STATUS: LEAD — not elevated to proven child.",
    ],
)
chana = add_person(
    "Chana Łazęga",
    "F",
    given="Chana",
    surname="Łazęga",
    birth="18 NOV 1897",
    birth_place="Nowy Korczyn, Poland",
    notes=["Birth act 100/1897 (6/18 Nov OS/NS). STATUS: ROOT."],
)

add_family(
    husb=abram_hersz,
    wife=laja,
    children=[szmul_laz, jozef_mendel, blima_lead, chana],
    marriage="17 DEC 1879",
    marriage_place="Nowy Korczyn, Poland",
    notes=[
        "Marriage act 44/1879 (5/17 Dec OS/NS).",
        "Blima 1896 is a lead only (dashed in tree).",
    ],
)

# ========== Feig / Braunstein ancestry ==========
jakob_feig = add_person("Jakob Feig", "M", given="Jakob", surname="Feig")
mesche_feig = add_person("Mesche Feig", "F", given="Mesche", surname="Feig")
markus_feig = add_person(
    "Markus Feig",
    "M",
    given="Markus",
    surname="Feig",
    birth="ABT 1831",
    death="25 NOV 1877",
    death_place="Klasno, Poland",
    occupancy="Butcher",
    notes=[
        "Death act 44/1877 age 46; parents Jakob and Mesche.",
        "STATUS: ROOT spouse-ancestry (Feig).",
    ],
)
breindl = add_person(
    "Breindl / Breindla Feig",
    "F",
    given="Breindl / Breindla",
    surname="Feig",
    aka=["Breindel"],
    notes=["Wife of Markus; mother of Hersch and siblings. STATUS: ROOT Feig."],
)
add_family(husb=jakob_feig, wife=mesche_feig, children=[markus_feig])

hersch_feig = add_person(
    "Hersch Feig",
    "M",
    given="Hersch",
    surname="Feig",
    birth="11 MAR 1863",
    birth_place="Klasno, Poland",
    occupancy="Butcher in Wieliczka",
    notes=["Klasno birth 1863; married 11 Sep 1887. STATUS: ROOT Feig."],
)
welman_feig = add_person(
    "Welman / Wolfman Feig",
    "M",
    given="Welman / Wolfman",
    surname="Feig",
    birth="19 MAY 1867",
    birth_place="Klasno, Poland",
    notes=["Klasno entry 209/1867; spelling Welman or Wolfman unresolved."],
)
mosche_feig = add_person(
    "Mosche Feig",
    "M",
    given="Mosche",
    surname="Feig",
    birth="15 MAY 1869",
    birth_place="Klasno, Poland",
)
rachel_feig_sib = add_person(
    "Rachel Feig",
    "F",
    given="Rachel",
    surname="Feig",
    birth="19 MAY 1871",
    birth_place="Klasno, Poland",
    notes=["Sister of Hersch; not Rachela wife of Józef Mendel."],
)
jacob_feig = add_person(
    "Jacob Feig",
    "M",
    given="Jacob",
    surname="Feig",
    birth="20 NOV 1872",
    birth_place="Klasno, Poland",
)
add_family(
    husb=markus_feig,
    wife=breindl,
    children=[hersch_feig, welman_feig, mosche_feig, rachel_feig_sib, jacob_feig],
    notes=["Confirmed siblings of Hersch from Klasno birth register."],
)

chaim_braun = add_person(
    "Chaim [surname unclear]",
    "M",
    given="Chaim",
    surname="",
    occupancy="Merchant in Mielec",
    notes=[
        "Maternal grandfather of Rachela Feig; surname not confidently legible on 1890 act.",
        "Earlier 'Feigl' expansion withdrawn.",
    ],
)
chana_braun = add_person(
    "Chana Braunstein",
    "F",
    given="Chana",
    surname="Braunstein",
    occupancy="Merchant in Mielec",
)
ryfka_braun = add_person(
    "Hinda / Ryfka Braunstein",
    "F",
    given="Hinda / Ryfka",
    surname="Braunstein",
    aka=["Ryfka Braun", "Ryfka Braunstein"],
    notes=[
        "Mother of Rachela Feig; residing Wieliczka 1890.",
        "STATUS: ROOT Feig maternal line.",
    ],
)
add_family(husb=chaim_braun, wife=chana_braun, children=[ryfka_braun])

rachela = add_person(
    "Rachela / Rachel Feig",
    "F",
    given="Rachela / Rachel",
    surname="Feig",
    birth="8 SEP 1890",
    birth_place="Wieliczka, Poland",
    notes=["Birth act 85/1890 Klasno-Podgórze register. STATUS: ROOT spouse."],
)
add_family(
    husb=hersch_feig,
    wife=ryfka_braun,
    children=[rachela],
    marriage="11 SEP 1887",
    marriage_place="Wieliczka / Klasno area",
    notes=["Hersch + Ryfka parents of Rachela."],
)

fryda = add_person(
    "Frajdla Łaja 'Fryda' Łazęga",
    "F",
    given="Frajdla Łaja",
    surname="Łazęga",
    birth="19 SEP 1912",
    aka=["Fryda", "Fryderika Rapaport (probable lead with conflict)"],
    notes=["Married Mendel Rapaport; child Abraham 1937. IPN wartime Kraków. STATUS: ROOT."],
)
henia = add_person(
    "Henryka 'Henia' Łazęga",
    "F",
    given="Henryka",
    surname="Łazęga",
    birth="23 NOV 1915",
    aka=["Henia", "Schachner (later identity)"],
    notes=["IPN wartime Kraków shelter. STATUS: ROOT."],
)
szyja = add_person(
    "Szymon / Szyja Beer 'Szijek' Łazęga",
    "M",
    given="Szymon / Szyja Beer",
    surname="Łazęga",
    birth="21 JUL 1918",
    birth_place="Kraków, Poland",
    aka=["Szijek", "Schije Lazega"],
    notes=["Paris emigration 1949; Częstochowa 1942; AJDC with Olga. STATUS: ROOT."],
)
jan_jakub = add_person(
    "Jan / Jakub Łazęga",
    "M",
    given="Jan / Jakub",
    surname="Łazęga",
    birth="2 JUL 1919",
    notes=["IPN wartime Kraków. STATUS: ROOT."],
)
mendel_rap = add_person(
    "Mendel Rapaport",
    "M",
    given="Mendel",
    surname="Rapaport",
    aka=["Mendel Rappaport"],
    notes=["Husband of Fryda; IPN wartime Kraków."],
)
abraham_rap = add_person(
    "Abraham Rapaport",
    "M",
    given="Abraham",
    surname="Rapaport",
    birth="1937",
    notes=["Son of Fryda and Mendel. STATUS: ROOT descendant."],
)
olga = add_person(
    "Olga Łazęga",
    "F",
    given="Olga",
    surname="Łazęga",
    notes=[
        "Appears with Szyja on AJDC/Arolsen; kinship degree NOT stated.",
        "STATUS: UNLINKED companion/contact — not merged as spouse/sibling.",
    ],
)

add_family(
    husb=jozef_mendel,
    wife=rachela,
    children=[fryda, henia, szyja, jan_jakub],
    notes=["STATUS: ROOT Kraków household."],
)
add_family(husb=mendel_rap, wife=fryda, children=[abraham_rap])

# ========== B. Herszla collateral (Mordka + Sora) ==========
mordka_old = add_person(
    "Mordka Łazęga",
    "M",
    given="Mordka",
    surname="Łazęga",
    notes=[
        "Father of Herszla; deceased before 1850. STATUS: SEPARATE collateral."
    ],
)
sora_moskow = add_person(
    "Sora Łazęga",
    "F",
    given="Sora",
    surname="Łazęga",
    aka=["Sora Moskow (patronymic/form)"],
    notes=["Mother of Herszla; form after Sora indexed as Moskow."],
)
herszla = add_person(
    "Herszla Łazęga",
    "M",
    given="Herszla",
    surname="Łazęga",
    birth="ABT 1779",
    death="24 JUN 1850",
    death_place="Nowy Korczyn, Poland",
    notes=[
        "Death act 14/1850 age 71; son of Mordka and Sora.",
        "STATUS: SEPARATE — not merged with Wulf/Beniamin.",
    ],
)
chwala = add_person(
    "Chwała Hercberg",
    "F",
    given="Chwała",
    surname="Hercberg",
    aka=["Chwała"],
)
ejzyk = add_person(
    "Ejzyk Herszlowicz Łazęga",
    "M",
    given="Ejzyk Herszlowicz",
    surname="Łazęga",
    birth="ABT 1804",
    birth_place="Nowy Korczyn, Poland",
    occupancy="Trader",
    aka=["Eyzik", "Icek", "Isaac"],
)
jozef_herszla = add_person(
    "Józef Łazęga",
    "M",
    given="Józef",
    surname="Łazęga",
    notes=["Named son of Herszla in 1850 death act; living Nowy Korczyn."],
)
abram_herszla = add_person(
    "Abram Łazęga",
    "M",
    given="Abram",
    surname="Łazęga",
    notes=[
        "Named son of Herszla in 1850 death act; living Nowy Korczyn.",
        "Not the same as Abram Chersz of the root line.",
    ],
)
chaja_herszla = add_person(
    "Chaja Łazęga",
    "F",
    given="Chaja",
    surname="Łazęga",
    notes=["Named daughter of Herszla in 1850 death act."],
)
fajgla_herszla = add_person(
    "Fajgla Łazęga",
    "F",
    given="Fajgla",
    surname="Łazęga",
    notes=["Named daughter of Herszla in 1850 death act."],
)
mania_herszla = add_person(
    "Mania Łazęga",
    "F",
    given="Mania",
    surname="Łazęga",
    notes=["Named daughter of Herszla in 1850 death act."],
)
haia_herszlowna = add_person(
    "Haia / Chaia Herszlowna Łazęga",
    "F",
    given="Haia / Chaia Herszlowna",
    surname="Łazęga",
    birth="ABT 1810",
    notes=["Married Abram Maier Pinkus 1834 act 6; parents Herszla + Chwała Hercberg."],
)
add_family(
    husb=mordka_old,
    wife=sora_moskow,
    children=[herszla],
    notes=["STATUS: SEPARATE older generation of Herszla branch."],
)
add_family(
    husb=herszla,
    wife=chwala,
    children=[
        ejzyk,
        jozef_herszla,
        abram_herszla,
        chaja_herszla,
        fajgla_herszla,
        mania_herszla,
        haia_herszlowna,
    ],
    notes=["Two additional sons mentioned in 1850 act not safely resolved."],
)

mosiek_wollman = add_person("Mosiek Wollman", "M", given="Mosiek", surname="Wollman")
sora_wollman = add_person(
    "Sora Wollman",
    "F",
    given="Sora",
    surname="Wollman",
    notes=["Surname for Sora uncertain/indexer-supplied in JRI; keep cautious."],
)
rachma = add_person(
    "Rachma / Rochema Wollman",
    "F",
    given="Rachma / Rochema",
    surname="Wollman",
    birth="ABT 1806",
)
add_family(husb=mosiek_wollman, wife=sora_wollman, children=[rachma])
mosiek_abram = add_person(
    "Mosiek Abram Łazęga",
    "M",
    given="Mosiek Abram",
    surname="Łazęga",
    birth="5 APR 1832",
    birth_place="Nowy Korczyn, Poland",
    notes=["Birth act 4/1832."],
)
add_family(
    husb=ejzyk,
    wife=rachma,
    children=[mosiek_abram],
    marriage="27 SEP 1826",
    marriage_place="Nowy Korczyn, Poland",
    notes=["Marriage act 6/1826."],
)

josek_pinkus = add_person("Josek Pinkus", "M", given="Josek", surname="Pinkus")
krajdla_wolman = add_person("Krajdla Wolman", "F", given="Krajdla", surname="Wolman")
abram_maier_pinkus = add_person(
    "Abram Maier Pinkus", "M", given="Abram Maier", surname="Pinkus", birth="ABT 1812"
)
add_family(husb=josek_pinkus, wife=krajdla_wolman, children=[abram_maier_pinkus])
add_family(
    husb=abram_maier_pinkus,
    wife=haia_herszlowna,
    marriage="22 JUL 1834",
    marriage_place="Nowy Korczyn, Poland",
    notes=["Marriage act 6/1834."],
)

# ========== C. Mortka/Ruchla Wiślica–Dębiany ==========
mortka_ruchla_f = add_person(
    "Mortka / Mordka Łazęga",
    "M",
    given="Mortka / Mordka",
    surname="Łazęga",
    birth="ABT 1810",
    death="BET 1862 AND 1866",
    occupancy="Merchant / grain merchant",
    notes=[
        "Alive at Małka 1862 marriage; deceased by Frymeta 1866 marriage.",
        "STATUS: SEPARATE Wiślica–Dębiany branch — not merged with Beniamin.",
    ],
)
ruchla = add_person(
    "Ruchla / Rochla Łazęga",
    "F",
    given="Ruchla / Rochla",
    surname="Łazęga",
    aka=["Ruchla Lewkowicz", "Rochla Tuchmajer"],
    notes=[
        "Maternal forms Lewkowicz (1846, 1866) and Tuchmajer (1852) both original.",
        "Alive 1866. STATUS: SEPARATE.",
    ],
)
icyk = add_person(
    "Icyk / Icek Łazęga",
    "M",
    given="Icyk / Icek",
    surname="Łazęga",
    birth="ABT 1841",
    birth_place="Wiślica, Poland",
    occupancy="Trader / colonist",
)
malka = add_person(
    "Małka Łazęga",
    "F",
    given="Małka",
    surname="Łazęga",
    birth="ABT 1843",
    birth_place="Dębiany, Poland",
)
frymet = add_person(
    "Frymet / Frymeta Łazęga",
    "F",
    given="Frymet / Frymeta",
    surname="Łazęga",
    birth="23 APR 1846",
    birth_place="Wiślica, Poland",
)
abram_infant = add_person(
    "Abram Łazęga",
    "M",
    given="Abram",
    surname="Łazęga",
    birth="12 JUN 1852",
    death="16 JUN 1852",
    birth_place="Wiślica, Poland",
    death_place="Wiślica, Poland",
    notes=["Birth act 35 and death act 9/1852; lived four days."],
)
lewek_lead = add_person(
    "Lewek Łazęga",
    "M",
    given="Lewek",
    surname="Łazęga",
    birth="ABT 1839",
    notes=[
        "JRI-Poland Wiślica index lead as child of Mordka/Rochla; not original-verified in report.",
        "STATUS: INDEX LEAD.",
    ],
)
chaja_1849_lead = add_person(
    "Chaja Łazęga",
    "F",
    given="Chaja",
    surname="Łazęga",
    birth="ABT 1849",
    notes=["JRI-Poland Wiślica index lead; not original-verified here. STATUS: INDEX LEAD."],
)
add_family(
    husb=mortka_ruchla_f,
    wife=ruchla,
    children=[lewek_lead, icyk, malka, frymet, chaja_1849_lead, abram_infant],
    notes=["Original-verified: Icyk, Małka, Frymet, Abram. Index leads: Lewek, Chaja."],
)

joachim_mend = add_person("Joachim Mendlowicz", "M", given="Joachim", surname="Mendlowicz")
itta_mend = add_person("Itta Mendlowicz", "F", given="Itta", surname="Mendlowicz")
kajla = add_person(
    "Kajla Laja Mendlowicz",
    "F",
    given="Kajla Laja",
    surname="Mendlowicz",
    birth="ABT 1841",
    birth_place="Byczów, Poland",
)
add_family(husb=joachim_mend, wife=itta_mend, children=[kajla])
dobra = add_person(
    "Dobra Rejla / Rojza Łazęga",
    "F",
    given="Dobra Rejla / Rojza",
    surname="Łazęga",
    birth="1 JAN 1861",
    birth_place="Wiślica, Poland",
    notes=["Birth act 1/1861; manuscript Rejla, JRI Rojza."],
)
bajla_etla = add_person(
    "Bajla Etla Łazęga",
    "F",
    given="Bajla Etla",
    surname="Łazęga",
    birth="6 DEC 1864",
    birth_place="Byczów, Poland",
)
haja_byczow = add_person(
    "Haja Łazęga",
    "F",
    given="Haja",
    surname="Łazęga",
    birth="27 DEC 1865",
    birth_place="Byczów, Poland",
)
add_family(
    husb=icyk,
    wife=kajla,
    children=[dobra, bajla_etla, haja_byczow],
    marriage="20 DEC 1859",
    marriage_place="Działoszyce, Poland",
    notes=["Marriage act 36/1859."],
)

helman_mil = add_person(
    "Helman / Zelman Milnarski",
    "M",
    given="Helman / Zelman",
    surname="Milnarski",
    aka=["Helman Milnarski", "Zelman Milnorski"],
    notes=["1862 original: Helman; JRI/index sometimes Zelman."],
)
rojza_mil = add_person("Rojza / Rajzla Milnarski", "F", given="Rojza / Rajzla", surname="Milnarski")
wolf_mil = add_person(
    "Wolf Milnarski",
    "M",
    given="Wolf",
    surname="Milnarski",
    birth="ABT 1844",
    birth_place="Kopernia, Poland",
    aka=["Wólf Milnorski"],
)
add_family(husb=helman_mil, wife=rojza_mil, children=[wolf_mil])
add_family(
    husb=wolf_mil,
    wife=malka,
    marriage="19 AUG 1862",
    marriage_place="Działoszyce, Poland",
    notes=["Marriage act 28/1862."],
)

symcha_pt = add_person(
    "Symcha Ptasznik", "M", given="Symcha", surname="Ptasznik", death="BEF 1866"
)
gitla_pt = add_person("Gitla Ptasznik", "F", given="Gitla", surname="Ptasznik")
wolf_pt = add_person("Wolf Ptasznik", "M", given="Wolf", surname="Ptasznik", birth="ABT 1846")
add_family(husb=symcha_pt, wife=gitla_pt, children=[wolf_pt])
add_family(
    husb=wolf_pt,
    wife=frymet,
    marriage="27 JAN 1866",
    marriage_place="Działoszyce, Poland",
    notes=["Marriage act 5/1866."],
)

# ========== D. Icek Boruch / Rosenberg ==========
abram_kwietner = add_person(
    "Abram Łazęga",
    "M",
    given="Abram",
    surname="Łazęga",
    notes=[
        "Father of Icek Boruch; spouse Szajndla Ita Kwietner.",
        "STATUS: SEPARATE — not Abram Chersz of root line.",
    ],
)
szajndla_kwiet = add_person(
    "Szajndla Ita Kwietner",
    "F",
    given="Szajndla Ita",
    surname="Kwietner",
    death="BEF AUG 1895",
)
icek_boruch = add_person(
    "Icek Boruch Łazęga",
    "M",
    given="Icek Boruch",
    surname="Łazęga",
    birth="ABT 1870",
    occupancy="Day laborer",
)
add_family(husb=abram_kwietner, wife=szajndla_kwiet, children=[icek_boruch])
majer_ros = add_person(
    "Majer Rosenberg", "M", given="Majer", surname="Rosenberg", death="BEF 1895"
)
mirela_gold = add_person("Mirela Goldman", "F", given="Mirela", surname="Goldman")
hendla_ros = add_person(
    "Hendla Rosenberg", "F", given="Hendla", surname="Rosenberg", birth="ABT 1871"
)
add_family(husb=majer_ros, wife=mirela_gold, children=[hendla_ros])
gitla_twin = add_person(
    "Gitla Łazęga",
    "F",
    given="Gitla",
    surname="Łazęga",
    birth="29 OCT 1895",
    birth_place="Nowy Korczyn, Poland",
    notes=["Twin; birth act 101/1895."],
)
laja_twin = add_person(
    "Laja Łazęga",
    "F",
    given="Laja",
    surname="Łazęga",
    birth="29 OCT 1895",
    birth_place="Nowy Korczyn, Poland",
    notes=["Twin; birth act 102/1895."],
)
add_family(
    husb=icek_boruch,
    wife=hendla_ros,
    children=[gitla_twin, laja_twin],
    marriage="21 AUG 1895",
    marriage_place="Nowy Korczyn, Poland",
    notes=["Marriage act 13/1895 (9/21 Aug OS/NS). Unlinked to Beniamin."],
)

# ========== E. Gersz / Kwietner ==========
gersz_laz = add_person(
    "Gersz Łazęga",
    "M",
    given="Gersz",
    surname="Łazęga",
    notes=["STATUS: SEPARATE Kwietner household."],
)
szili_mirla = add_person("Szili Mirla Kwietner", "F", given="Szili Mirla", surname="Kwietner")
josel = add_person(
    "Josel / Josek Łazęga",
    "M",
    given="Josel / Josek",
    surname="Łazęga",
    birth="ABT JUN 1894",
    death="30 AUG 1894",
    death_place="Nowy Korczyn, Poland",
    notes=["Death act 131/1894 age 2 months."],
)
add_family(husb=gersz_laz, wife=szili_mirla, children=[josel])

# ========== F. Icek / Świczarczyk (Chmielnik) ==========
abram_kwiatek = add_person(
    "Abram Łazęga",
    "M",
    given="Abram",
    surname="Łazęga",
    notes=[
        "Husband of Szajndla Kwiatek; father of Icek of Chmielnik.",
        "STATUS: SEPARATE — chronology rules out identity with Abram Chersz.",
    ],
)
szajndla_kwiatek = add_person(
    "Szajndla Kwiatek", "F", given="Szajndla", surname="Kwiatek", death="BEF 1892"
)
icek_chmiel = add_person(
    "Icek Łazęga",
    "M",
    given="Icek",
    surname="Łazęga",
    birth="ABT 1871",
    occupancy="Merchant/trader",
)
add_family(husb=abram_kwiatek, wife=szajndla_kwiatek, children=[icek_chmiel])
abram_lejzer_sw = add_person(
    "Abram Lejzer Świczarczyk", "M", given="Abram Lejzer", surname="Świczarczyk"
)
estera_ita_raj = add_person("Estera Ita Raj", "F", given="Estera Ita", surname="Raj")
cyrla_sw = add_person(
    "Cyrla Świczarczyk", "F", given="Cyrla", surname="Świczarczyk", birth="ABT 1870"
)
add_family(husb=abram_lejzer_sw, wife=estera_ita_raj, children=[cyrla_sw])
lejb_laz = add_person(
    "Lejb / Lejba / Liba Łazęga",
    "M",
    given="Lejb / Lejba",
    surname="Łazęga",
    birth="22 OCT 1894",
    birth_place="Nowy Korczyn, Poland",
    occupancy="Laborer",
    notes=["Łódź registration 1919 as Liba; same person as Lejb."],
)
szulim = add_person(
    "Szulim Bejer Łazęga",
    "M",
    given="Szulim Bejer",
    surname="Łazęga",
    birth="13 NOV 1898",
    birth_place="Chmielnik, Poland",
    notes=["Birth act 252/1898 (1/13 Nov OS/NS)."],
)
add_family(
    husb=icek_chmiel,
    wife=cyrla_sw,
    children=[lejb_laz, szulim],
    marriage="14 AUG 1892",
    marriage_place="Chmielnik, Poland",
    notes=["Marriage act 30/1892 (2/14 Aug OS/NS)."],
)

# ========== G. Jakub / Roter ==========
jakub_roter = add_person(
    "Jakub Łazęga",
    "M",
    given="Jakub",
    surname="Łazęga",
    birth="ABT 1863",
    occupancy="Trader / melamed",
    notes=["Indexed maternal surname Zylberberg. STATUS: SEPARATE Chmielnik–NK cluster."],
)
curtla_roter = add_person(
    "Curtla Roter",
    "F",
    given="Curtla",
    surname="Roter",
    birth="ABT 1865",
    notes=["Indexed maternal surname Dzura."],
)
szajndla_1900 = add_person(
    "Szajndla Łazęga",
    "F",
    given="Szajndla",
    surname="Łazęga",
    birth="ABT 1900",
    notes=["Child of Jakub + Curtla Roter per consolidated map."],
)
kalman = add_person(
    "Kalman / Kalma Łazęga",
    "M",
    given="Kalman / Kalma",
    surname="Łazęga",
    birth="5 AUG 1901",
    birth_place="Nowy Korczyn, Poland",
    notes=["Birth act 72/1901 (23 Jul/5 Aug OS/NS)."],
)
add_family(
    husb=jakub_roter,
    wife=curtla_roter,
    children=[szajndla_1900, kalman],
    marriage="28 FEB 1887",
    marriage_place="Chmielnik, Poland",
    notes=["Marriage act 14/1887 (16/28 Feb OS/NS)."],
)

jakub_hamer = add_person(
    "Jakub Łazęga",
    "M",
    given="Jakub",
    surname="Łazęga",
    birth="ABT 1863",
    occupancy="Religious teacher (melamed)",
    notes=[
        "Husband of Curtla Hamer/Hammer — NOT merged with Jakub+Roter.",
        "STATUS: SEPARATE namesake household.",
    ],
)
curtla_hamer = add_person(
    "Curtla Hamer / Hammer",
    "F",
    given="Curtla",
    surname="Hamer",
    aka=["Curtla Hammer"],
    birth="ABT 1865",
)
izrajel = add_person(
    "Izrajel Łazęga",
    "M",
    given="Izrajel",
    surname="Łazęga",
    birth="ABT 1905",
    notes=["Son of Jakub + Curtla Hamer/Hammer."],
)
add_family(
    husb=jakub_hamer,
    wife=curtla_hamer,
    children=[izrajel],
    notes=["Mothers' surnames prevent merger with Roter household."],
)

# ========== H. Alter / Luft ==========
alter_luft = add_person(
    "Alter Łazęga",
    "M",
    given="Alter",
    surname="Łazęga",
    birth="ABT 1865",
    occupancy="Shoemaker",
    notes=["Older Alter; spouse Cylka Mirla Luft. STATUS: SEPARATE."],
)
cylka_luft = add_person("Cylka Mirla Luft", "F", given="Cylka Mirla", surname="Luft")
szmul_herszel = add_person(
    "Szmul Herszel / Herszla Łazęga",
    "M",
    given="Szmul Herszel / Herszla",
    surname="Łazęga",
    birth="ABT 1885",
)
add_family(husb=alter_luft, wife=cylka_luft, children=[szmul_herszel])
laja_swicz = add_person(
    "Laja Świczarczyk",
    "F",
    given="Laja",
    surname="Świczarczyk",
    birth="ABT 1885",
    birth_place="Chmielnik, Poland",
    notes=["Married Szmul Herszel; parents named in act (father given name not certain in report)."],
)
szlama_dawid = add_person(
    "Szlama Dawid Łazęga", "M", given="Szlama Dawid", surname="Łazęga", birth="ABT 1911"
)
add_family(
    husb=szmul_herszel,
    wife=laja_swicz,
    children=[szlama_dawid],
    notes=["Marriage ~1909 per report chronology."],
)

# ========== I. Younger Alter / Wilczyk ==========
chaja_bajla_mother = add_person(
    "Chaja Bajla Łazęga",
    "F",
    given="Chaja Bajla",
    surname="Łazęga",
    notes=[
        "Mother of younger Alter; father unknown in report.",
        "STATUS: SEPARATE — not older Alter/Luft.",
    ],
)
alter_wilczyk = add_person(
    "Alter Łazęga",
    "M",
    given="Alter",
    surname="Łazęga",
    birth="ABT 1868",
    occupancy="Carter/driver",
    notes=[
        "Younger Alter; bachelor until marriage to Sora Estera Wilczyk.",
        "Different chronology from older Alter+Luft.",
    ],
)
add_family(wife=chaja_bajla_mother, children=[alter_wilczyk], notes=["Father of Alter unknown."])
sora_estera = add_person(
    "Sora Estera Wilczyk", "F", given="Sora Estera", surname="Wilczyk", birth="ABT 1868"
)
chaim_1899 = add_person("Chaim Łazęga", "M", given="Chaim", surname="Łazęga", birth="ABT 1899")
golda_twin = add_person("Gołda Łazęga", "F", given="Gołda", surname="Łazęga", birth="ABT 1905")
abram_twin = add_person("Abram Łazęga", "M", given="Abram", surname="Łazęga", birth="ABT 1905")
add_family(
    husb=alter_wilczyk,
    wife=sora_estera,
    children=[chaim_1899, golda_twin, abram_twin],
    marriage="ABT 1898",
    marriage_place="Nowy Korczyn, Poland",
    notes=["Married 1898/1899; twins Gołda and Abram 1905."],
)

# ========== J. Small households / unplaced ==========
abram_stark = add_person(
    "Abram Łazęga",
    "M",
    given="Abram",
    surname="Łazęga",
    notes=["Husband of Esta Stark; father of Chaja Basza. STATUS: UNLINKED household."],
)
esta_stark = add_person("Esta Stark", "F", given="Esta", surname="Stark")
chaja_basza = add_person(
    "Chaja Basza / Basia Łazęga",
    "F",
    given="Chaja Basza / Basia",
    surname="Łazęga",
    birth="ABT 1823",
    death="28 APR 1896",
    death_place="Nowy Korczyn, Poland",
    notes=["Death act 10/1896 age 73."],
)
add_family(husb=abram_stark, wife=esta_stark, children=[chaja_basza])

chaja_liksz = add_person(
    "Chaja Łazęga",
    "F",
    given="Chaja",
    surname="Łazęga",
    birth="ABT 1876",
    notes=[
        "Mother of Rywka Likszenberg 1896; parents not named in birth act. STATUS: UNLINKED."
    ],
)
pinchas_liksz = add_person(
    "Pinchas / Pinkas Likszenberg",
    "M",
    given="Pinchas / Pinkas",
    surname="Likszenberg",
    birth="ABT 1871",
    occupancy="Merchant/trader",
)
rywka_liksz = add_person(
    "Rywka Likszenberg",
    "F",
    given="Rywka",
    surname="Likszenberg",
    birth="31 AUG 1896",
    birth_place="Nowy Korczyn, Poland",
    notes=["Birth act 105/1896 (19/31 Aug OS/NS)."],
)
add_family(husb=pinchas_liksz, wife=chaja_liksz, children=[rywka_liksz])

mortka_prop = add_person(
    "Mortka Łazęga",
    "M",
    given="Mortka",
    surname="Łazęga",
    notes=[
        "Father of Majzel? Lazenga; different mother (Laja Propinator) from Małka's Mortka/Rochla.",
        "STATUS: SEPARATE — identity with other Mortkas unproven.",
    ],
)
laja_prop = add_person("Laja Propinator", "F", given="Laja", surname="Propinator")
majzel = add_person(
    "Majzel? Lazenga",
    "M",
    given="Majzel?",
    surname="Lazenga",
    birth="ABT 1851",
    notes=[
        "Włoszczowa marriage no. 2/1875 age 24; question mark in source.",
        "JRI Kielce-Radom SIG Journal vol.7 no.1 2003.",
    ],
)
add_family(husb=mortka_prop, wife=laja_prop, children=[majzel])
naftula = add_person(
    "Naftula Krasowska",
    "M",
    given="Naftula",
    surname="Krasowska",
    notes=[
        "Report: daughter Matla Hawa's parents Naftula and Tauba Krasowska — surname assignment follow source cautiously."
    ],
)
tauba = add_person("Tauba Krasowska", "F", given="Tauba", surname="Krasowska")
matla = add_person(
    "Matla Hawa Wajntrob", "F", given="Matla Hawa", surname="Wajntrob", birth="ABT 1855"
)
add_family(
    husb=naftula,
    wife=tauba,
    children=[matla],
    notes=["Parents of Matla Hawa per indexed marriage."],
)
add_family(
    husb=majzel,
    wife=matla,
    marriage="1875",
    marriage_place="Włoszczowa, Poland",
    notes=["Marriage no. 2/1875."],
)

herszli_1819 = add_person(
    "Herszli Łazęga",
    "M",
    given="Herszli",
    surname="Łazęga",
    notes=["Father of Sura 1819 New Miasto. STATUS: NEW INDEX LEAD."],
)
laja_zelman = add_person("Laja Zelmanowicz", "F", given="Laja", surname="Zelmanowicz")
sura_1819 = add_person(
    "Sura Łazęga",
    "F",
    given="Sura",
    surname="Łazęga",
    birth="12 DEC 1819",
    birth_place="Nowy Korczyn / New Miasto, Poland",
    aka=["Lazegowna"],
    notes=["Geneteka birth index act 82/1819."],
)
add_family(husb=herszli_1819, wife=laja_zelman, children=[sura_1819])
cetla = add_person(
    "Cetla Łazęga",
    "F",
    given="Cetla",
    surname="Łazęga",
    notes=["Mother of Toba Fiuk 1824; parents unknown. STATUS: INDEX LEAD."],
)
herszli_fiuk = add_person(
    "Herszli Fiuk",
    "M",
    given="Herszli",
    surname="Fiuk",
    notes=["Father of Toba Fiuk; not proven same as Herszli Łazęga of Sura."],
)
toba_fiuk = add_person(
    "Toba Fiuk",
    "F",
    given="Toba",
    surname="Fiuk",
    birth="20 JAN 1824",
    birth_place="Nowy Korczyn / New Miasto, Poland",
    notes=["Geneteka act 19/1824; mother Cetla Łazęga."],
)
add_family(husb=herszli_fiuk, wife=cetla, children=[toba_fiuk])

wolf_berk = add_person(
    "Wolf Berkowicz",
    "M",
    given="Wolf",
    surname="Berkowicz",
    notes=[
        "Father of Mortka Berkowicz 1814; surname is Berkowicz not Łazęga.",
        "STATUS: REJECTED as Wolf Łazęga identity.",
    ],
)
rochla_laz_mother = add_person(
    "Rochla Łazęga",
    "F",
    given="Rochla",
    surname="Łazęga",
    notes=[
        "Mother of Mortka Berkowicz 1814 New Miasto act 55.",
        "Does not establish Wolf's surname as Łazęga.",
    ],
)
mortka_berk = add_person(
    "Mortka Berkowicz",
    "M",
    given="Mortka",
    surname="Berkowicz",
    birth="9 JUL 1814",
    birth_place="Nowy Korczyn / New Miasto, Poland",
    notes=["Geneteka act 55/1814."],
)
add_family(
    husb=wolf_berk,
    wife=rochla_laz_mother,
    children=[mortka_berk],
    notes=["Rejected as Wolf Łazęga identity on present evidence."],
)

jozef_chawa = add_person(
    "Józef Łazęga",
    "M",
    given="Józef",
    surname="Łazęga",
    occupancy="Baker (Chmielnik)",
    notes=[
        "Chmielnik bakery household; probable match to 1929 'Łazęga J.' baker.",
        "Memorial list LAZENGA Yosef etc. STATUS: UNLINKED secondary source.",
    ],
)
chawa_wife = add_person(
    "Chawa Łazęga",
    "F",
    given="Chawa",
    surname="Łazęga",
    notes=["Wife in Chmielnik commemorative household with Józef."],
)
tova_ch = add_person(
    "Tova / Gitl Łazęga",
    "F",
    given="Tova / Gitl",
    surname="Łazęga",
    notes=["Commemorative/secondary Chmielnik household child."],
)
kalman_ch = add_person(
    "Kalman Łazęga",
    "M",
    given="Kalman",
    surname="Łazęga",
    notes=["Commemorative list; identity with 1901 Kalman unproven."],
)
zvi_ch = add_person("Zvi / Hershl Łazęga", "M", given="Zvi / Hershl", surname="Łazęga")
estera_ch = add_person("Estera / Esther Łazęga", "F", given="Estera / Esther", surname="Łazęga")
moshe_ch = add_person("Moshe Łazęga", "M", given="Moshe", surname="Łazęga")
bella_ch = add_person("Bella Łazęga", "F", given="Bella", surname="Łazęga")
add_family(
    husb=jozef_chawa,
    wife=chawa_wife,
    children=[tova_ch, kalman_ch, zvi_ch, estera_ch, moshe_ch, bella_ch],
    notes=["Modern secondary commemorative source p.237; relationships approximate."],
)

wiktor = add_person(
    "Wiktor Lazega",
    "M",
    given="Wiktor",
    surname="Lazega",
    birth="1895",
    birth_place="Kraków, Poland",
    notes=["Kraków survivor-list; UNLINKED."],
)
jozef_1915 = add_person(
    "Józef Lazega",
    "M",
    given="Józef",
    surname="Lazega",
    birth="1915",
    birth_place="Kraków, Poland",
    notes=["1915 survivor-list entry — NOT Józef Mendel born 1887. UNLINKED."],
)
jakob_plaszow = add_person(
    "Jakob Lazęga",
    "M",
    given="Jakob",
    surname="Lazęga",
    notes=["KL Płaszów database; ŻIH card. UNLINKED."],
)
sala = add_person(
    "Sala Łazęga / Wolkowitz",
    "F",
    given="Sala",
    surname="Łazęga",
    birth="15 APR 1922",
    birth_place="Chmielnik, Poland",
    aka=["Sala Wolkowitz"],
    notes=["Bergen-Belsen list exact date. UNLINKED surname occurrence."],
)
idzia = add_person(
    "Idzia / Judyta / Idesa Łazęga",
    "F",
    given="Idzia / Judyta / Idesa",
    surname="Łazęga",
    birth="18 JUN 1924",
    birth_place="Będzin, Poland",
    notes=["Very probable match to 1939 Będzin census Idesa; parents not stated. UNLINKED."],
)
szlama_surv = add_person(
    "Szlama Łazęga",
    "M",
    given="Szlama",
    surname="Łazęga",
    notes=["1945 survivor registry with Nowy Korczyn; relationships not proved. UNLINKED."],
)
fela = add_person(
    "Fela Łazęga",
    "F",
    given="Fela",
    surname="Łazęga",
    notes=["Survivor registry Langenbielau. UNLINKED."],
)
pola = add_person(
    "Pola Łazęga",
    "F",
    given="Pola",
    surname="Łazęga",
    notes=["Survivor registry Langenbielau. UNLINKED."],
)
hella = add_person(
    "Hella / Diamant",
    "F",
    given="Hella",
    surname="Diamant",
    notes=["Survivor-list contact evidence; not treated as family relationship. UNLINKED contact."],
)
moschek = add_person(
    "Moschek",
    "M",
    given="Moschek",
    surname="",
    notes=["Survivor-list contact; no proved parentage. UNLINKED."],
)
majera = add_person(
    "Majer Łazęga",
    "M",
    given="Majer",
    surname="Łazęga",
    notes=["Szczekociny surname occurrence; no proved parentage. UNLINKED."],
)
sara_unl = add_person(
    "Sara Łazęga",
    "F",
    given="Sara",
    surname="Łazęga",
    notes=["Wartime/survivor surname case. UNLINKED."],
)
ida_unl = add_person(
    "Ida Łazęga",
    "F",
    given="Ida",
    surname="Łazęga",
    notes=["Wartime/survivor surname case. UNLINKED."],
)
sura_sally = add_person(
    "Sura / Sally Łazęga",
    "F",
    given="Sura / Sally",
    surname="Łazęga",
    notes=["Wartime/survivor surname case. UNLINKED."],
)


def esc(s):
    return (s or "").replace("@", "@@")


def ged_safe_name(s):
    """GEDCOM uses / to delimit surname; never leave raw slashes in name parts."""
    return esc((s or "").replace(" / ", " or ").replace("/", " or "))


def write_notes(lines, nlist):
    for n in nlist:
        if len(n) <= 200:
            lines.append(f"1 NOTE {esc(n)}")
        else:
            lines.append(f"1 NOTE {esc(n[:200])}")
            rest = n[200:]
            while rest:
                lines.append(f"2 CONC {esc(rest[:200])}")
                rest = rest[200:]


lines = []
lines.append("0 HEAD")
lines.append("1 SOUR Nowy_Korczyn_Lazega_family_research_REORGANIZED_2026-07-17")
lines.append("2 NAME Łazęga family research — reorganized evidence report")
lines.append("2 VERS 2026-07-17")
lines.append("1 DEST OTHER")
lines.append("1 DATE " + date.today().strftime("%d %b %Y").upper())
lines.append("1 FILE Nowy_Korczyn_Lazega_family_REORGANIZED_2026-07-17.ged")
lines.append("1 GEDC")
lines.append("2 VERS 5.5.1")
lines.append("2 FORM LINEAGE-LINKED")
lines.append("1 CHAR UTF-8")
lines.append("1 NOTE Extracted from the reorganized Łazęga research PDF (17 July 2026).")
lines.append("2 CONT Root, collateral, and unlinked households are preserved as separate families.")
lines.append("2 CONT Surname alone never creates a connection. See NOTE tags for STATUS.")
lines.append("2 CONT Source PDF: Nowy_Korczyn_Lazega_family_research_REORGANIZED_2026-07-17.pdf")

for i, p in people.items():
    lines.append(f"0 @{i}@ INDI")
    g = ged_safe_name(p["given"])
    s = ged_safe_name(p["surname"])
    if s:
        lines.append(f"1 NAME {g} /{s}/")
    else:
        lines.append(f"1 NAME {g} //")
    if g:
        lines.append(f"2 GIVN {g}")
    if s:
        lines.append(f"2 SURN {s}")
    for a in p["aka"]:
        # aka may be full display names without surname slashes
        aka = ged_safe_name(a)
        if "/" not in a and " " in a.strip():
            parts = a.strip().rsplit(" ", 1)
            lines.append(f"1 NAME {ged_safe_name(parts[0])} /{ged_safe_name(parts[1])}/")
        else:
            lines.append(f"1 NAME {aka}")
        lines.append("2 TYPE also known as")
    if p["sex"] in ("M", "F"):
        lines.append(f"1 SEX {p['sex']}")
    if p["birth"]:
        lines.append("1 BIRT")
        lines.append(f"2 DATE {p['birth']}")
        if p["birth_place"]:
            lines.append(f"2 PLAC {esc(p['birth_place'])}")
    if p["death"]:
        lines.append("1 DEAT")
        lines.append(f"2 DATE {p['death']}")
        if p["death_place"]:
            lines.append(f"2 PLAC {esc(p['death_place'])}")
    if p["occupancy"]:
        lines.append(f"1 OCCU {esc(p['occupancy'])}")
    if p["famc"]:
        lines.append(f"1 FAMC @{p['famc']}@")
    for f in p["fams"]:
        lines.append(f"1 FAMS @{f}@")
    write_notes(lines, p["notes"])

for f, fam in families.items():
    lines.append(f"0 @{f}@ FAM")
    if fam["husb"]:
        lines.append(f"1 HUSB @{fam['husb']}@")
    if fam["wife"]:
        lines.append(f"1 WIFE @{fam['wife']}@")
    for c in fam["children"]:
        lines.append(f"1 CHIL @{c}@")
    if fam["marriage"]:
        lines.append("1 MARR")
        lines.append(f"2 DATE {fam['marriage']}")
        if fam["marriage_place"]:
            lines.append(f"2 PLAC {esc(fam['marriage_place'])}")
    write_notes(lines, fam["notes"])

lines.append("0 TRLR")
OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
# Also drop a copy beside the source PDF in Downloads when present.
downloads = Path(r"C:\Users\Avi Schwartz\Downloads") / OUT.name
try:
    downloads.write_text(OUT.read_text(encoding="utf-8"), encoding="utf-8")
except OSError:
    downloads = None
print(f"Wrote {OUT}")
if downloads:
    print(f"Copied {downloads}")
print(f"Individuals: {len(people)}")
print(f"Families: {len(families)}")
