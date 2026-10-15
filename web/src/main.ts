import { mount } from 'svelte'
import '@fontsource/ibm-plex-sans/400.css'
import '@fontsource/ibm-plex-sans/500.css'
import '@fontsource/ibm-plex-sans/600.css'
import '@fontsource/ibm-plex-mono/400.css'
import '@fontsource/ibm-plex-mono/500.css'
import './lib/theme.css'
import App from './App.svelte'

export default mount(App, { target: document.getElementById('app')! })
