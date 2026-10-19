"""Invented device map and acoustic fixtures for UI review, never real hardware."""
from __future__ import annotations

import json
from itertools import count
from pathlib import Path

import numpy as np

from . import equipment, measurements
from .engine import Engine, EngineError
from .mapping import ChannelAddrs, DeviceMapping, channel_response, XO_BIQUAD_SLOTS, XO_FIRST_ORDER_SLOTS
from .model import CHANNELS, EQ_BANDS, Crossover, Role, Tune

DEMO_MARKER = '.helix-unwound-demo.json'


class DemoMapping(DeviceMapping):
    synthetic = True

    def __init__(self):
        # Deliberately invented contiguous addresses, unrelated to any vendor map.
        addresses = count(1)
        def section(keys):
            return {key: next(addresses) for key in keys}
        self.master = next(addresses)
        self.channels = [ChannelAddrs(
            eq=[section(('B2', 'B1', 'B0', 'A2', 'A1')) for _ in range(EQ_BANDS)],
            xo_bq=[section(('B2', 'B1', 'B0', 'A2', 'A1')) for _ in range(XO_BIQUAD_SLOTS)],
            xo_fo=[section(('B1', 'B0', 'A1')) for _ in range(XO_FIRST_ORDER_SLOTS)],
            delay=next(addresses), invert=next(addresses), gain=next(addresses),
            mute=next(addresses), mix=section(('L', 'R')),
        ) for _ in CHANNELS]


def create_demo_engine(data_dir: Path) -> Engine:
    data_dir = data_dir.expanduser().resolve()
    if data_dir.exists() and not data_dir.is_dir():
        raise EngineError('Demo data path must be a directory; existing file was not changed')
    marker = data_dir / DEMO_MARKER
    if marker.exists():
        if json.loads(marker.read_text()) != {'version': 1, 'seeded': True}:
            raise EngineError('Incomplete or unsupported demo data; choose a new empty demo directory')
        return Engine(mapping=DemoMapping(), data_dir=data_dir)
    if data_dir.exists() and any(data_dir.iterdir()):
        raise EngineError('Demo requires an empty directory or existing demo state; existing files were not changed')
    data_dir.mkdir(parents=True, exist_ok=True)
    # Mark before creating any other state. Partial initialisation refuses reuse.
    marker.write_text(json.dumps({'version': 1, 'seeded': False}))
    tune = Tune(name='Demo · virtual three-way + subs', master_gain_db=-9)
    bands = {'A': (Role.MIDBASS, 65, 300), 'B': (Role.MIDBASS, 65, 300),
             'C': (Role.MIDRANGE, 300, 3000), 'D': (Role.MIDRANGE, 300, 3000),
             'E': (Role.TWEETER, 3000, None), 'F': (Role.TWEETER, 3000, None),
             'I': (Role.SUBWOOFER, 25, 70), 'J': (Role.SUBWOOFER, 25, 70)}
    for cid, (role, hp, lp) in bands.items():
        ch = tune.channel(cid)
        ch.role, ch.name, ch.gain_db = role, f"{'Left' if cid in 'ACEI' else 'Right'} {role.value}", -6
        ch.hp = Crossover(freq_hz=hp)
        ch.lp = Crossover(freq_hz=lp) if lp else None
        ch.mix = {'L' if cid in 'ACEI' else 'R': 1}
    for cid in 'GH':
        tune.channel(cid).mute = True
    # Replace the prototype seed inventory; no personal equipment or microphone serials.
    design = equipment.SystemDesign()
    source = equipment.Component(id='demo-source', kind='source', name='Synthetic stereo source')
    dsp = equipment.Component(id='demo-dsp', kind='dsp', name='Virtual ten-output DSP')
    amp = equipment.Component(id='demo-amp', kind='amplifier', name='Virtual amplifier bank')
    mic = equipment.Component(id='demo-mic', kind='microphone', name='Synthetic microphone · no captured audio')
    design.components = [source, dsp, amp, mic]
    design.connections.append(equipment.Connection(src=source.id, dst=dsp.id, signal='line'))
    for cid, (role, _, _) in bands.items():
        driver = equipment.Component(id=f'demo-driver-{cid}', kind='subwoofer' if role == Role.SUBWOOFER else 'speaker',
            name=tune.channel(cid).name, make='Synthetic', model=f'Virtual {role.value}', channels=[cid],
            notes='Generated example; no physical driver or datasheet')
        design.components.append(driver)
        design.connections.extend([
            equipment.Connection(src=dsp.id, src_port=f'out{cid}', dst=amp.id, dst_port=f'in{cid}', signal='line'),
            equipment.Connection(src=amp.id, src_port=f'out{cid}', dst=driver.id, dst_port='in', signal='speaker')])
    (data_dir / 'system.json').write_text(design.model_dump_json(indent=2))
    engine = Engine(mapping=DemoMapping(), data_dir=data_dir, tune=tune)
    engine.save_design(design)
    engine._autosave()
    engine.save_snapshot('Demo baseline')
    grid = measurements.GRID
    for cid in bands:
        response = channel_response(tune.channel(cid), tune.sample_rate, grid)
        peak = 6 * np.exp(-np.log2(grid / (500 if cid in 'CDEF' else 110)) ** 2 / 0.12)
        spl = 84 + response + tune.master_gain_db + peak
        m = measurements.Measurement(id=f'demo-{cid}', name=f'Synthetic {tune.channel(cid).name}', channels=[cid],
            taken_at=0, source='Generated mathematical fixture, not microphone audio',
            notes='Demo hardware identities and curves are invented; not hardware validation.',
            freqs=grid.tolist(), spl=spl.tolist(), tune=tune.model_copy(deep=True),
            drivers={cid: engine.driver_identity(cid)}, drivers_source='Synthetic demo fixture, not owner attestation')
        engine.measurements.save(m)
    marker.write_text(json.dumps({'version': 1, 'seeded': True}))
    return engine
