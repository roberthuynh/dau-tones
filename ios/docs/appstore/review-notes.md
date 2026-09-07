# App Review notes: VietQuest

VietQuest is an offline Vietnamese learning app for English-speaking adult beginners and
heritage learners. This build contains a complete Southern Vietnamese café mission and the
existing Northern/Southern tone practice tools. It is an initial course release, not a complete
multi-level language curriculum or a certification of conversational proficiency.

**How to try it:** launch, choose beginner or heritage preparation, and start the café mission.
Listen to the question, practice an order, ask for repetition, and change your order when
coffee is unavailable. Recording and replay are optional; meaning choices allow microphone-free
practice. Learn also contains the tone trainer and word library. No account, sign-in, purchases,
or remote service is required.

**Privacy:** the app collects no data and performs no tracking. It makes no network requests.
Microphone audio is processed on-device and never transmitted. Café practice recordings are
temporary local files for immediate replay and are discarded when the practice ends. Practice
history and settings stay on-device (declared in the bundled privacy manifest, reason CA92.1). This is why
the App Privacy section is answered "Data Not Collected". The app is fully functional in
airplane mode.

**Speech recognition** (where used) is pinned to on-device recognition. If a device does not
have Vietnamese dictation installed, the affected screen falls back to a prompted mode that uses
only the app's own analysis — it never falls back to server recognition.

**Reference audio** is partly synthesized. Café teaching audio is prerecorded AI-generated
speech, bundled for offline playback. Tone feedback is a limited signal-based coaching aid;
neither transcript agreement nor choosing a response proves spoken intelligibility.
