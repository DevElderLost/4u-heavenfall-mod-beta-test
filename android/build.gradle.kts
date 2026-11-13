plugins {
    id("com.android.application") version "8.7.3" apply false
    id("org.jetbrains.kotlin.android") version "2.1.0" apply false
    id("org.jetbrains.kotlin.plugin.compose") version "2.1.0" apply false
    // Python 3.13 inside the app: the same version the program's CI and requirements.txt use
    id("com.chaquo.python") version "17.1.0" apply false
}
