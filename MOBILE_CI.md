# Empaquetado móvil

NOVA Studio usa Capacitor y scripts shell portables. GitHub Actions solo aporta
los runners; el empaquetado también puede ejecutarse en runners propios,
Forgejo Actions, Woodpecker, Jenkins u otro CI.

## Artefactos automáticos

- Cada pull request que toca código móvil genera un APK Android instalable de
  depuración y un IPA iOS sin firma.
- Cada push a `main` con cambios móviles vuelve a validar ambos paquetes.
- Un tag `mobile-v*` publica ambos archivos en GitHub Releases.
- `workflow_dispatch` permite ejecutar el pipeline manualmente.

El repositorio es público, por lo que los runners estándar de GitHub Actions
son gratuitos. No hace falta registrar otro servicio ni añadir una tarjeta.

## Backend

El paquete incluye el frontend, pero usa un backend HTTPS remoto. El valor por
defecto es `https://video.byrongonzalez.dev`.

Para cambiarlo:

1. Configura la variable de repositorio `NOVA_API_BASE_URL`; o
2. Indica `api_base_url` al lanzar el workflow manual; o
3. Ejecuta localmente con `NOVA_API_BASE_URL=https://api.example.com`.

El backend debe permitir los orígenes `https://localhost` para Android y
`capacitor://localhost` para iOS.

## Ejecución local

Requisitos comunes: Node.js 22 o superior y `npm ci`.

Android requiere JDK 17 o superior y Android SDK 36:

```bash
npm run mobile:android
```

iOS requiere macOS con Xcode 26 o superior:

```bash
npm run mobile:ios
```

Los resultados se escriben en `artifacts/mobile`.

## Firmas

El APK de depuración se puede instalar directamente, pero no es una firma de
producción estable.

El IPA confirma que el proyecto iOS compila y queda empaquetado, pero no se
puede instalar en un dispositivo ni publicar en TestFlight/App Store porque no
tiene firma. Apple exige una cuenta de desarrollador, un certificado y un
perfil de aprovisionamiento para distribuir una aplicación iOS; esa exigencia
no se puede sustituir con un servicio gratuito sin registro.
