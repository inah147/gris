// Inicialização do PWA para GRIS
(function() {
  'use strict';

  function isMobileViewport() {
    return window.matchMedia('(max-width: 768px)').matches;
  }

  function showBasecoatToast(config) {
    if (!document.getElementById('toaster')) return false;
    document.dispatchEvent(new CustomEvent('basecoat:toast', { detail: { config } }));
    return true;
  }

  function setGrisFavicon() {
    const head = document.head || document.getElementsByTagName('head')[0];
    if (!head) {
      return;
    }

    const icons = [
      { rel: 'shortcut icon', href: '/assets/gris/images/icons/favicon/32.png', type: 'image/png' },
      { rel: 'icon', href: '/assets/gris/images/icons/favicon/16.png', type: 'image/png', sizes: '16x16' },
      { rel: 'icon', href: '/assets/gris/images/icons/favicon/32.png', type: 'image/png', sizes: '32x32' }
    ];

    head.querySelectorAll('link[rel="icon"], link[rel="shortcut icon"]').forEach((link) => {
      link.remove();
    });

    icons.forEach((icon) => {
      const link = document.createElement('link');
      link.rel = icon.rel;
      link.href = icon.href;
      link.type = icon.type;
      if (icon.sizes) {
        link.sizes = icon.sizes;
      }
      head.appendChild(link);
    });
  }

  setGrisFavicon();

  if (window.location.pathname === '/login' || window.location.pathname.startsWith('/login/')) {
    document.body.classList.add('gris-login-page');
  }

  // Verifica se o browser suporta Service Workers
  if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
      navigator.serviceWorker
        .register('/assets/gris/js/service-worker.js')
        .then(registration => {
          console.log('[PWA] Service Worker registrado com sucesso:', registration.scope);
          
          // Verifica atualizações
          registration.addEventListener('updatefound', () => {
            const newWorker = registration.installing;
            newWorker.addEventListener('statechange', () => {
              if (newWorker.state === 'installed' && navigator.serviceWorker.controller) {
                // Nova versão disponível
                console.log('[PWA] Nova versão disponível!');
                // Você pode adicionar uma notificação para o usuário aqui
                showUpdateNotification();
              }
            });
          });
        })
        .catch(error => {
          console.error('[PWA] Erro ao registrar Service Worker:', error);
        });
    });
  }

  // Função para mostrar notificação de atualização
  function showUpdateNotification() {
    showBasecoatToast({
      category: 'info',
      title: __('Uma nova versão do app está disponível. Recarregue para atualizar.'),
      duration: -1,
      action: {
        label: __('Recarregar'),
        onclick: 'window.location.reload()'
      }
    });
  }

  // Detecta quando o app é instalado
  window.addEventListener('appinstalled', () => {
    console.log('[PWA] App instalado com sucesso!');
    showBasecoatToast({
      category: 'success',
      title: __('Gris foi instalado com sucesso!'),
      duration: 5000
    });
  });

  // Prompt de instalação
  let deferredPrompt;
  
  window.addEventListener('beforeinstallprompt', (e) => {
    // Previne o prompt automático
    e.preventDefault();
    deferredPrompt = e;
    
    // Mostra um botão de instalação customizado
    showInstallPromotion();
  });

  function showInstallPromotion() {
    if (!isMobileViewport()) {
      return;
    }

    if (window.location.pathname !== '/inicio') {
      return;
    }

    if (!frappe.session || frappe.session.user === 'Guest') {
      return;
    }

    showBasecoatToast({
      category: 'info',
      title: __('Instale o Gris no seu dispositivo!'),
      duration: -1,
      action: {
        label: __('Instalar'),
        onclick: 'window.installPWA()'
      },
      cancel: {
        label: __('Fechar'),
        onclick: ''
      }
    });
  }

  // Função global para instalar o PWA
  window.installPWA = function() {
    if (deferredPrompt) {
      deferredPrompt.prompt();
      deferredPrompt.userChoice.then((choiceResult) => {
        if (choiceResult.outcome === 'accepted') {
          console.log('[PWA] Usuário aceitou a instalação');
        } else {
          console.log('[PWA] Usuário recusou a instalação');
        }
        deferredPrompt = null;
      });
    }
  };

  // Detecta se está rodando como PWA instalado
  function isRunningStandalone() {
    return (window.matchMedia('(display-mode: standalone)').matches) 
      || (window.navigator.standalone) 
      || document.referrer.includes('android-app://');
  }

  if (isRunningStandalone()) {
    console.log('[PWA] Rodando como app instalado');
    // Adicione estilos ou comportamentos específicos para o modo standalone
    document.body.classList.add('pwa-standalone');
  }

})();
