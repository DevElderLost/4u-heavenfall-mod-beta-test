plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
    id("com.chaquo.python")
}

// The repository's root: android/ sits inside it, and the app builds the mod with the repository's own `core` package.
val repoRoot: File = rootProject.projectDir.parentFile
val coreAssets: File = layout.buildDirectory.dir("generated/heavenfall/assets").get().asFile

// `core` (the mod's code and data) as one zip inside the APK, with the same skips as the web page's bundle
// (tools/release/build_web.py: BUNDLE_SKIPS_*). The app unpacks it on first start (HeavenfallBridge.unpackCode):
// the code reads its data files by path, so it needs real files rather than Chaquopy's in-APK modules.
val zipCore = tasks.register<Zip>("zipHeavenfallCore") {
    from(File(repoRoot, "core")) {
        into("core")
        exclude(
            "gui/qt/**", "interface/game_gui/recorder/**", "**/__pycache__/**",
            "**/*.pyc", "**/*.c", "**/*.h", "**/*.s", "**/*.ld",
        )
    }
    archiveFileName.set("heavenfall-core.zip")
    destinationDirectory.set(coreAssets)
}
tasks.configureEach {
    if (name.contains("Assets") || name.startsWith("lint")) {
        dependsOn(zipCore)
    }
}

android {
    namespace = "io.github.develderlost.heavenfall"
    compileSdk = 35

    defaultConfig {
        applicationId = "io.github.develderlost.heavenfall"
        minSdk = 24                 // Chaquopy 17's minimum
        targetSdk = 35
        versionCode = 1
        versionName = "0.1.2"       // keep equal to core/__init__.py
        ndk {
            // Phones are arm64; x86_64 is for the emulator. -Pheavenfall.abis=arm64-v8a makes the APK smaller.
            val abis = providers.gradleProperty("heavenfall.abis").orNull
            abiFilters += (abis ?: "arm64-v8a,x86_64").split(",")
        }
    }

    sourceSets {
        getByName("main") {
            assets.srcDir(coreAssets)
        }
    }

    // A fixed key, when the CI has one (HF_KEYSTORE...): an APK signed with it installs over the previous one.
    // Without it the debug key of the machine is used, which changes from one CI run to the next.
    signingConfigs {
        val keystore = System.getenv("HF_KEYSTORE")
        if (keystore != null && File(keystore).exists()) {
            create("ci") {
                storeFile = File(keystore)
                storePassword = System.getenv("HF_KEYSTORE_PASSWORD")
                keyAlias = System.getenv("HF_KEY_ALIAS")
                keyPassword = System.getenv("HF_KEY_PASSWORD")
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            signingConfig = signingConfigs.findByName("ci") ?: signingConfigs.getByName("debug")
        }
        debug {
            signingConfigs.findByName("ci")?.let { signingConfig = it }
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }
    buildFeatures {
        compose = true
    }
    lint {
        checkReleaseBuilds = false
        abortOnError = false
    }
    packaging {
        resources {
            excludes += "/META-INF/{AL2.0,LGPL2.1}"
        }
    }
}

chaquopy {
    defaultConfig {
        version = "3.13"
        // Only .zcci/.zcxi/.zcia (Azahar's compressed files) need zstandard, and Chaquopy has no wheel of it for
        // every Python version: build with -Pheavenfall.zstd=true once one exists for 3.13 to read them in the app.
        if (providers.gradleProperty("heavenfall.zstd").orNull == "true") {
            pip {
                install("zstandard")
            }
        }
    }
}

dependencies {
    implementation(platform("androidx.compose:compose-bom:2024.12.01"))
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.material:material-icons-core")
    implementation("androidx.activity:activity-compose:1.9.3")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.8.7")
    implementation("androidx.core:core-ktx:1.15.0")
    implementation("androidx.documentfile:documentfile:1.0.1")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.9.0")
}
