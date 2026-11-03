# Range hood Smart ventilate and air-quality controls

Verified on the AHD-WW-TP1-22-COMMON family, 2026-11-02.

`/airlevelcheck/vs/0` accepts partial writes to
`x.com.samsung.da.periodicSensingActivationState` (On/Off),
`x.com.samsung.da.autoExeState` (Sensing/Alarm/Airpurify),
`x.com.samsung.da.periodicSensingSkipStatus` (On/Off), and
`x.com.samsung.da.periodicSensingSkipTime` (HHMMHHMM).

The app labels are Detection only, Get notifications and Quietly ventilate.
Sensing is valid and writable even when omitted from supportedAutoExeState.
The master switch preserves the configured mode. A 2.04 echo or immediate GET
is insufficient verification: the first GET can still show the old value.
Delayed reads confirmed these settings both through raw writes and HA entities.

The hood's DND window is UTC: a saved 22:00–05:00 app window at UTC-8 reports
06001300. HA reads the next UTC occurrence as an aware datetime and localizes
it in the time platform; payload_fn converts local writes back to UTC, preserving
the other half of the packed window. The purifier's existing wall-clock field
keeps its original semantics.

Dust/FineDust/SuperFineDust are PM10/PM2.5/PM1.0. Values are
`[concentration, grade]`, with concentrations in HA's canonical μg/m³ (U+03BC).
The hood-specific grades are 1 Good, 2 Normal, 3 Poor, 4 Very poor. Enum sensors
read that grade directly, rather than calculating thresholds. Other appliance
families can have different grade floors; this mapping is intentionally scoped
to the hood. Grade 10 is a transient Processing state: recorder captured it in
all three grades during two cycles, and a direct one-shot capture reproduced it
before valid grades returned. It is translated as Processing (internal enum key processing), not a fifth
quality band; concentrations remain numeric. The three concentration descriptor
keys remain stable.

All nine shipped language catalogs include the new names and enum states.
The old periodic-air-sensing binary sensor and automatic-ventilation-state sensor
are superseded by writable controls; existing installations can remove their
orphan registry entries after auditing consumers.

The interval field is displayed as a read-only duration: 1800 was acknowledged
but ignored, 7200 persisted, and 3600 was restored. Supported bounds and an actual
two-hour sampling cadence are not established. One-shot sensing was not exposed as an entity. A later direct capture verified
that startSensingOnce triggers Processing and transient grade 10; the original
request flag was restored after the experiment.

No sound/mute control was found in the current cloud capabilities, local resource
directories, mode options or 21 targeted sound endpoint probes (all 4.04).
DND suppresses air analysis during the window; it is not a general chime-mute
contract. Unadvertised Volume tokens or opaque option-code bits were not written
without an original value and a known inverse. An internal firmware command
would require separate firmware/captured-command evidence.

Edge lighting advertised supported conditions without an active condition;
keep-normal semantics remained opaque; after-run returned only progress on this
unit. Those reads do not justify inventing user controls.

References:
- [SmartThings capability contracts](https://developer.smartthings.com/docs/devices/capabilities)
- [SmartThings presentations](https://developer.smartthings.com/docs/devices/capabilities/capability-presentations)
- [Samsung four-level air-quality bands](https://www.samsung.com/au/support/home-appliances/have-cleaner-air-with-the-samsung-air-purifier/)

HA Core SmartThings uses six named cloud health-concern states, not the local
four-band grade codes, and supplies no mapping for grade 10 or lastSensingLevel.
The published custom.periodicSensing capability describes lastSensingLevel as a
string without an enum. On this hood, 129 aligned recorder rows showed Kr1–Kr4
matching CleanLevel 1–4; that supports an ordinal relationship but does not
publish Samsung labels for these regional codes. Per user direction, map Kr1–Kr4
to Good/Normal/Poor/Very poor using the hood's observed ordinal relationship;
preserve unknown codes. This is the stored last result, not the live PM grade.

CleanLevel is now a hood-specific four-band enum (1 Good, 2 Normal, 3 Poor,
4 Very poor), with unknown codes preserved. History matched Kr1/Kr2/Kr3/Kr4
on all 117 valid rows (41/29/20/27 respectively). This is inferred from the
ordinal correspondence and Samsung four-band ordering, not a published firmware
contract. It is not necessarily the worst current PM grade. No unit/state class
is assigned; other appliance families retain their existing CleanLevel behavior.

Independent review covered the full feature diff and this note. No confirmed
functional bugs or blocking findings were identified; 314 independently selected
tests passed. The implementer's full suite had 2673 passes and one pre-existing
credential identity test failure, reproduced on the starting commit. Ordinary
summer/winter conversion is tested; DST transition-day writes, seasonal device
behavior and native-speaker translation review remain unverified.
