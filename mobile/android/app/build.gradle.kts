plugins {
    id("com.android.application")
    id("kotlin-android")
    id("dev.flutter.flutter-gradle-plugin")
}

android {
    namespace = "com.wowai.app"
    compileSdk = flutter.compileSdkVersion
    ndkVersion = flutter.ndkVersion

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = JavaVersion.VERSION_17.toString()
    }

    defaultConfig {
        // WOW AI Phase 1 will eventually request call-screening / telephony
        // roles here (CALL_SCREENING_SERVICE, ROLE_CALL_SCREENING) - not
        // requested yet, since Phase 1 does not do real call handling.
        applicationId = "com.wowai.app"
        minSdk = 26
        targetSdk = flutter.targetSdkVersion
        versionCode = flutter.versionCode
        versionName = flutter.versionName
    }

    buildTypes {
        release {
            signingConfig = signingConfigs.getByName("debug")
        }
    }
}

flutter {
    source = "../.."
}

dependencies {
    // Phase 2 Block 6: androidx.core.app.ActivityCompat / androidx.core.content.ContextCompat
    // used by MainActivity's runtime permission requests and
    // CallStateObserver's permission check - standard, foundational
    // AndroidX support library, not an unrelated addition.
    implementation("androidx.core:core-ktx:1.13.1")
}
