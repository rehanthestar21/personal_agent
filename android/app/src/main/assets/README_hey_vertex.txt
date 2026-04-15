To enable "Hey Vertex" wake word:

1. Sign up at https://console.picovoice.ai/ and get an AccessKey.
2. Create a custom wake word "Hey Vertex" in the console and download the .ppn file.
3. Place the file here as: hey_vertex.ppn
4. Add to your project's gradle.properties (or local.properties):
   PICOVOICE_ACCESS_KEY=your_access_key_here
   Then in app/build.gradle.kts defaultConfig add:
   buildConfigField("String", "PICOVOICE_ACCESS_KEY", "\"${project.findProperty("PICOVOICE_ACCESS_KEY") ?: ""}\"")

Or set the build config field directly in build.gradle.kts (do not commit the key).
