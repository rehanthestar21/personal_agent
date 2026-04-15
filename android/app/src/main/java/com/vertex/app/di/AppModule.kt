package com.vertex.app.di

import android.content.Context
import com.vertex.app.BuildConfig
import com.vertex.app.audio.SpeechRecognizerWrapper
import com.vertex.app.audio.TextToSpeechEngine
import com.vertex.app.network.VertexApi
import com.vertex.app.network.VertexApiClient
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.android.qualifiers.ApplicationContext
import dagger.hilt.components.SingletonComponent
import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import java.util.concurrent.TimeUnit
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
object AppModule {

    @Provides
    @Singleton
    fun provideOkHttp(): OkHttpClient {
        return OkHttpClient.Builder()
            .connectTimeout(15, TimeUnit.SECONDS)
            .readTimeout(120, TimeUnit.SECONDS)
            .writeTimeout(15, TimeUnit.SECONDS)
            .addInterceptor(
                HttpLoggingInterceptor().apply {
                    level = HttpLoggingInterceptor.Level.HEADERS
                }
            )
            .build()
    }

    @Provides
    @Singleton
    fun provideRetrofit(client: OkHttpClient): Retrofit {
        return Retrofit.Builder()
            .baseUrl(BuildConfig.DEFAULT_BACKEND_URL)
            .client(client)
            .addConverterFactory(GsonConverterFactory.create())
            .build()
    }

    @Provides
    @Singleton
    fun provideVertexApi(retrofit: Retrofit): VertexApi {
        return retrofit.create(VertexApi::class.java)
    }

    @Provides
    @Singleton
    fun provideApiClient(api: VertexApi, client: OkHttpClient): VertexApiClient {
        return VertexApiClient(api, client)
    }

    @Provides
    @Singleton
    fun provideTts(@ApplicationContext context: Context): TextToSpeechEngine {
        return TextToSpeechEngine(context)
    }

    @Provides
    @Singleton
    fun provideSpeechRecognizerWrapper(@ApplicationContext context: Context): SpeechRecognizerWrapper {
        return SpeechRecognizerWrapper(context)
    }

}
