"""Local audio evidence and descriptive comparisons, never hardware authority.

Input metrics are untrusted. No result proves an isolated guitar, a device
recording, aligned performances, physical loudness or an audible tone match.
"""
import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator


class Measurements(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    url: str | None = Field(default=None, max_length=2048)
    file_name: str | None = Field(default=None, max_length=180)
    sample_seconds: float = Field(gt=0, le=60)
    start_seconds: float = Field(default=0, ge=0, le=86400)
    source_seconds: float | None = Field(default=None, gt=0, le=86400)
    rms_dbfs: float = Field(ge=-200, le=40)
    peak_dbfs: float = Field(ge=-200, le=40)
    crest_db: float = Field(ge=0, le=200)
    centroid_hz: float = Field(ge=0, le=24000)
    band_energy: list[float] = Field(min_length=5, max_length=5)
    analysis_method: Literal['legacy-v1', 'channel-power-v2'] = 'legacy-v1'
    analysis_rate_hz: StrictInt | None = Field(default=None, ge=8000, le=192000)
    analysis_cutoff_hz: float | None = Field(default=None, gt=0, le=7000)
    analysis_channels: StrictInt | None = Field(default=None, ge=1, le=8)
    analysis_frames: StrictInt | None = Field(default=None, ge=1, le=512)

    @model_validator(mode='after')
    def within_source(self):
        if self.source_seconds is not None and self.start_seconds+self.sample_seconds>self.source_seconds+.001:
            raise ValueError('Measured audio window extends beyond its source')
        if self.analysis_method=='channel-power-v2':
            if self.analysis_rate_hz!=16000 or self.analysis_cutoff_hz is None or self.analysis_channels is None or self.analysis_frames is None:
                raise ValueError('Channel-power v2 requires its exact rate, channel and frame provenance')
            if (any(not math.isfinite(x) or not 0<=x<=1 for x in self.band_energy)
                    or not .99<=math.fsum(self.band_energy)<=1.01
                    or self.rms_dbfs>self.peak_dbfs+.01
                    or abs(self.crest_db-(self.peak_dbfs-self.rms_dbfs))>.1
                    or self.centroid_hz>8000):
                raise ValueError('Inconsistent channel-power v2 measurements')
        elif any(v is not None for v in (self.analysis_rate_hz,self.analysis_cutoff_hz,self.analysis_channels,self.analysis_frames)):
            raise ValueError('Legacy audio measurements cannot claim v2 provenance')
        return self


def private_evidence(value):
    """Keep bounded numeric evidence only, not URLs or local file names."""
    reading=value if isinstance(value,Measurements) else Measurements.model_validate(value)
    return reading.model_dump(exclude={'url','file_name'})


class Comparison(BaseModel):
    model_config=ConfigDict(extra='forbid')
    reference: Measurements
    recording: Measurements


def compare(body: Comparison):
    """Describe recording minus reference; no score, action or auto gain boost."""
    target, actual=body.reference,body.recording
    if target.analysis_method!='channel-power-v2' or actual.analysis_method!='channel-power-v2':
        raise ValueError('Measure both clips again using channel-power v2 before comparing')
    if abs(target.analysis_cutoff_hz-actual.analysis_cutoff_hz)>.01:
        raise ValueError('Use clips with the same spectral filter cutoff before comparing')
    if min(target.rms_dbfs,actual.rms_dbfs)<-120:
        raise ValueError('A silent or near-silent clip is not a usable comparison')
    names=('0-250 Hz','250-600 Hz','600-2000 Hz','2000-5000 Hz','5000-8000 Hz')
    return dict(hardware_written=False,
        reference=private_evidence(target),recording=private_evidence(actual),
        differences=dict(rms_db=actual.rms_dbfs-target.rms_dbfs,
            peak_db=actual.peak_dbfs-target.peak_dbfs,
            crest_db=actual.crest_db-target.crest_db,
            centroid_hz=actual.centroid_hz-target.centroid_hz,
            band_energy=[dict(band=name,delta_fraction=b-a,
                relative_db=10*math.log10(b/a) if a>0 and b>0 else None)
                for name,a,b in zip(names,target.band_energy,actual.band_energy)]),
        audible_match_verified=False,isolated_guitar_verified=False,
        performance_alignment_verified=False,unit_recording_verified=False,
        note='Beschrijvende opname minus referentie. Andere noten, aanslag, instrumenten en opnameketen kunnen deze verschillen veroorzaken. Geen klankscore, automatische gaincorrectie, AI-beluistering of bewijs van fysieke luidheid.')
