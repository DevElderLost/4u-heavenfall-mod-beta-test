// Heavenfall Beta for Android: the installer as an app (Jetpack Compose on top of the program's own Python code,
// run by Chaquopy). Build: see android/README.md.
pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
        maven("https://chaquo.com/maven")
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
        maven("https://chaquo.com/maven")
    }
}

rootProject.name = "HeavenfallAndroid"
include(":app")
