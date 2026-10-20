"""Net CO2 of electricity from imported wood pellets vs coal and natural gas (South Korea case).

Everything is computed per MWh of electricity. Parameters carry their source in PARAMS_SOURCES.
Biogenic CO2 is shown explicitly: the net result depends on how fast the forest re-absorbs it.
"""
import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
os.makedirs(OUT, exist_ok=True)

# ---- parameters -------------------------------------------------------------
LHV_PELLET_GJ_T = 17.0          # GJ per tonne pellets (assumption: typical, ~16.5-18; check ISO 17225-2)
EF_BIOGENIC = 112.0             # kg CO2/GJ, IPCC 2006 Vol.2 Table 2.2, wood/wood waste (range 95-132)
EF_COAL = 96.1                  # kg CO2/GJ, IPCC 2006 sub-bituminous coal (range 92.8-100)
EF_GAS = 56.1                   # kg CO2/GJ, IPCC 2006 natural gas (range 54.3-58.3)
ETA = {"pellet": 0.33, "coal": 0.38, "gas": 0.55}   # assumptions, varied in sensitivity
# supply chain, kg CO2e per tonne pellets (Jonker et al. 2014, GCB Bioenergy 6:371-389)
PELLETISING = 160.0
FEEDSTOCK = 78.0                # silviculture, medium intensity (range 30-96)
INLAND = 62.3 + 9.1             # truck 100 km + rail
SEA_KG_PER_TKM = 0.008          # assumption; GLEC 2023 bulk carrier >200k dwt = 0.0027, smaller ships higher
SEA_KM = {"Russia": 1000, "Vietnam": 4000, "Indonesia": 4500, "Canada": 9500}  # approximate distances
SEA_KM_DEFAULT = SEA_KM["Vietnam"]
# Origin-specific regrowth time T (years) and 2025 import shares (Lesprom). Malaysia (6 %) has no T and is left out;
# shares are renormalised over the four origins below.
#   Vietnam   6 (5-12): acacia plantations, 5-12 yr rotations, Vo Thi Hai & La Thi (2024), Tropentag
#   Indonesia 6 (5-8) : Eucalyptus pellita 6-yr cycle, Iswanto et al. (2021) JMHT 27(3); range is an assumption
#   Canada    70 (55-100): MAI culmination age of lodgepole pine / white spruce in north-central BC, Lalumiere et al. (2019)
#   Russia    100 (60-150): ASSUMPTION; Shvidenko reports mean coniferous stand age ~115 yr, not a rotation age
ORIGINS = {
    "Vietnam":   {"km": 4000, "T": 6,   "T_lo": 5,  "T_hi": 12,  "share": 0.37},
    "Indonesia": {"km": 4500, "T": 6,   "T_lo": 5,  "T_hi": 8,   "share": 0.23},
    "Russia":    {"km": 1000, "T": 100, "T_lo": 60, "T_hi": 150, "share": 0.16},
    "Canada":    {"km": 9500, "T": 70,  "T_lo": 55, "T_hi": 100, "share": 0.12},
}
REGROWTH_YEARS_DEFAULT = 30     # years for forest to re-absorb the biogenic CO2 (assumption)
J = 3.6                          # GJ per MWh

def supply_kg_per_t(sea_km=SEA_KM_DEFAULT, sea_f=SEA_KG_PER_TKM):
    return PELLETISING + FEEDSTOCK + INLAND + sea_km * sea_f

def per_mwh(eta, ef):                       # kg CO2 per MWh_el for a fuel with factor ef (kg/GJ)
    return ef * J / eta

def pellet_split(sea_km=SEA_KM_DEFAULT, sea_f=SEA_KG_PER_TKM, eta=None, lhv=LHV_PELLET_GJ_T):
    eta = eta or ETA["pellet"]
    fuel_gj = J / eta
    supply = supply_kg_per_t(sea_km, sea_f) / lhv * fuel_gj
    biogenic = EF_BIOGENIC * fuel_gj
    return supply, biogenic

def net_pellet(horizon, regrowth_years=REGROWTH_YEARS_DEFAULT, **kw):
    """Supply chain + the share of biogenic CO2 not yet re-absorbed after `horizon` years (linear regrowth)."""
    supply, bio = pellet_split(**kw)
    unabsorbed = np.clip(1 - np.asarray(horizon, dtype=float) / regrowth_years, 0, 1)
    return supply + bio * unabsorbed

def parity_horizon(comparator, regrowth_years=REGROWTH_YEARS_DEFAULT, **kw):
    """Years after which pellet electricity emits no more than the comparator (None if never)."""
    supply, bio = pellet_split(**kw)
    if supply >= comparator:
        return None
    return regrowth_years * (1 - (comparator - supply) / bio)

def origin_parity(name, T=None):
    o = ORIGINS[name]; coal = per_mwh(ETA["coal"], EF_COAL)
    return parity_horizon(coal, T or o["T"], sea_km=o["km"])

def mix_net(horizon):
    """Import-share-weighted net emission (kg CO2/MWh) for the four origins at their own T."""
    tot = sum(o["share"] for o in ORIGINS.values())
    return sum(o["share"] / tot * net_pellet(horizon, o["T"], sea_km=o["km"]) for o in ORIGINS.values())

def mix_parity(comparator, hmax=200):
    hs = np.arange(0, hmax + 0.01, 0.1)
    ok = np.where(mix_net(hs) <= comparator)[0]
    return float(hs[ok[0]]) if len(ok) else None

if __name__ == "__main__":
    coal = per_mwh(ETA["coal"], EF_COAL)
    gas = per_mwh(ETA["gas"], EF_GAS)
    supply, bio = pellet_split()
    rows = [("Coal (combustion only)", coal), ("Natural gas (combustion only)", gas),
            ("Pellets: supply chain only (IPCC convention, biogenic = 0)", supply),
            ("Pellets: biogenic CO2 at stack", bio),
            ("Pellets: supply chain + all biogenic (no re-absorption)", supply + bio)]
    pd.DataFrame(rows, columns=["case", "kg_CO2_per_MWh_el"]).round(0).to_csv(f"{OUT}/baseline.csv", index=False)

    # 1) origin-specific results
    tot = sum(o["share"] for o in ORIGINS.values())
    orows = []
    for n, o in ORIGINS.items():
        sup_o, _ = pellet_split(sea_km=o["km"])
        orows.append((n, o["km"], o["T"], o["T_lo"], o["T_hi"], round(o["share"] / tot, 3), round(sup_o, 0),
                      round(origin_parity(n), 1), round(origin_parity(n, o["T_lo"]), 1), round(origin_parity(n, o["T_hi"]), 1)))
    odf = pd.DataFrame(orows, columns=["origin", "sea_km", "T_years", "T_low", "T_high", "share_of_four", "supply_kg_per_MWh",
                                       "parity_vs_coal_yr", "parity_at_T_low", "parity_at_T_high"])
    odf.to_csv(f"{OUT}/origin_results.csv", index=False)
    mp_coal, mp_gas = mix_parity(coal), mix_parity(gas)
    pd.DataFrame([("import-weighted mix", mp_coal, mp_gas, float(mix_net(0)), float(mix_net(10)), float(mix_net(30)))],
                 columns=["case", "parity_vs_coal_yr", "parity_vs_gas_yr", "net_at_0yr", "net_at_10yr", "net_at_30yr"]).round(1).to_csv(f"{OUT}/mix_results.csv", index=False)

    # 2) figure
    H = np.arange(0, 101)
    fig, ax = plt.subplots(1, 3, figsize=(15, 4.6))
    cols = {"Vietnam": "#2a9d8f", "Indonesia": "#8ab17d", "Russia": "#e76f51", "Canada": "#6d597a"}
    for n, o in ORIGINS.items():
        ax[0].plot(H, net_pellet(H, o["T"], sea_km=o["km"]), color=cols[n], label=f"{n} (T={o['T']} yr)")
    ax[0].plot(H, mix_net(H), color="k", lw=2.5, label="import-weighted mix")
    ax[0].axhline(coal, color="k", ls="--", lw=1, label="coal"); ax[0].axhline(gas, color="grey", ls=":", label="natural gas")
    ax[0].set(xlabel="Time horizon (years)", ylabel="kg CO2 per MWh electricity", title="Net pellet emissions by origin")
    ax[0].legend(fontsize=7)
    names = list(ORIGINS); y0 = np.arange(len(names))
    base = [origin_parity(n) for n in names]
    lo = [origin_parity(n, ORIGINS[n]["T_lo"]) for n in names]; hi = [origin_parity(n, ORIGINS[n]["T_hi"]) for n in names]
    ax[1].barh(y0, base, color=[cols[n] for n in names])
    ax[1].errorbar(base, y0, xerr=[np.array(base) - np.array(lo), np.array(hi) - np.array(base)], fmt="none", ecolor="k", capsize=3)
    ax[1].axvline(mp_coal, color="k", ls="--", lw=1); ax[1].text(mp_coal, len(names) - 0.4, f" mix {mp_coal:.0f} yr", fontsize=8)
    ax[1].set_yticks(y0); ax[1].set_yticklabels(names); ax[1].invert_yaxis()
    ax[1].set(xlabel="Years until pellets <= coal (bar: baseline T; whisker: T range)", title="Parity horizon vs coal")
    labels = ["Coal", "Gas", "Pellets\nsupply only", "Pellets\n+ biogenic"]
    ax[2].bar(labels[0], coal, color="#555"); ax[2].bar(labels[1], gas, color="#999")
    ax[2].bar(labels[2], supply, color="#2a9d8f")
    ax[2].bar(labels[3], supply, color="#2a9d8f", label="supply chain"); ax[2].bar(labels[3], bio, bottom=supply, color="#e76f51", label="biogenic CO2")
    ax[2].set(ylabel="kg CO2 per MWh electricity", title="Baseline (pellets from Vietnam)"); ax[2].legend(fontsize=8)
    plt.tight_layout(); plt.savefig(f"{OUT}/biomass_carbon.png", dpi=150)
    print(odf.to_string()); print(pd.read_csv(f"{OUT}/mix_results.csv").to_string())

    # 4) sensitivity: 30-yr regrowth assumed, net emission after a 10-year horizon
    sens = []
    def add(name, val, **kw):
        T = kw.get("regrowth_years", REGROWTH_YEARS_DEFAULT)
        k2 = {a: b for a, b in kw.items() if a != "regrowth_years"}
        sens.append((name, val, float(net_pellet(10, T, **k2)), parity_horizon(coal, T, **k2)))
    add("baseline", "-")
    for T in (10, 60): add("regrowth years", T, regrowth_years=T)
    for e in (0.28, 0.38): add("pellet efficiency", e, eta=e)
    for f in (0.0027, 0.013): add("sea kg CO2/t-km", f, sea_f=f)
    for l in (16.0, 18.0): add("LHV GJ/t", l, lhv=l)
    pd.DataFrame(sens, columns=["parameter", "value", "net_kg_per_MWh_10yr_horizon", "parity_yr_vs_coal"]).round(1).to_csv(f"{OUT}/sensitivity.csv", index=False)

    print(pd.read_csv(f"{OUT}/baseline.csv")); print(pd.read_csv(f"{OUT}/sensitivity.csv"))
    print("parity vs coal (Vietnam), T=5,30,60,100:", [round(parity_horizon(coal, T), 1) for T in (5, 30, 60, 100)])
