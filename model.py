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

if __name__ == "__main__":
    coal = per_mwh(ETA["coal"], EF_COAL)
    gas = per_mwh(ETA["gas"], EF_GAS)
    supply, bio = pellet_split()
    rows = [("Coal (combustion only)", coal), ("Natural gas (combustion only)", gas),
            ("Pellets: supply chain only (IPCC convention, biogenic = 0)", supply),
            ("Pellets: biogenic CO2 at stack", bio),
            ("Pellets: supply chain + all biogenic (no re-absorption)", supply + bio)]
    pd.DataFrame(rows, columns=["case", "kg_CO2_per_MWh_el"]).round(0).to_csv(f"{OUT}/baseline.csv", index=False)

    # 1) net emission vs time horizon for several regrowth times
    H = np.arange(0, 101)
    fig, ax = plt.subplots(1, 3, figsize=(15, 4.6))
    for T, c in [(5, "#2a9d8f"), (30, "#e9c46a"), (60, "#e76f51"), (100, "#6d597a")]:
        ax[0].plot(H, net_pellet(H, T), label=f"regrowth {T} yr", color=c)
    ax[0].axhline(coal, color="k", ls="--", label="coal"); ax[0].axhline(gas, color="grey", ls=":", label="natural gas")
    ax[0].set(xlabel="Time horizon (years)", ylabel="kg CO2 per MWh electricity", title="Net pellet emissions vs horizon")
    ax[0].legend(fontsize=8)

    # 2) parity horizon vs regrowth time, by origin
    Ts = np.arange(5, 101, 5); rows2 = []
    for name, km in SEA_KM.items():
        ys = [parity_horizon(coal, T, sea_km=km) for T in Ts]
        ax[1].plot(Ts, ys, label=f"{name} ({km} km)")
        rows2 += [(name, km, T, y) for T, y in zip(Ts, ys)]
    ax[1].set(xlabel="Forest regrowth time (years)", ylabel="Years until pellets <= coal", title="Parity horizon vs coal")
    ax[1].legend(fontsize=8)
    pd.DataFrame(rows2, columns=["origin", "sea_km", "regrowth_years", "parity_years_vs_coal"]).round(1).to_csv(f"{OUT}/parity_horizon.csv", index=False)

    # 3) stacked baseline bars
    labels = ["Coal", "Gas", "Pellets\nsupply only", "Pellets\n+ biogenic"]
    ax[2].bar(labels[0], coal, color="#555"); ax[2].bar(labels[1], gas, color="#999")
    ax[2].bar(labels[2], supply, color="#2a9d8f")
    ax[2].bar(labels[3], supply, color="#2a9d8f", label="supply chain"); ax[2].bar(labels[3], bio, bottom=supply, color="#e76f51", label="biogenic CO2")
    ax[2].set(ylabel="kg CO2 per MWh electricity", title="Baseline (pellets from Vietnam)"); ax[2].legend(fontsize=8)
    plt.tight_layout(); plt.savefig(f"{OUT}/biomass_carbon.png", dpi=150)

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
