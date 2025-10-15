// Inicialização do PWA para GRIS
(function() {
  'use strict';

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
    if (frappe && frappe.show_alert) {
      frappe.show_alert({
        message: __('Uma nova versão do app está disponível. Recarregue a página para atualizar.'),
        indicator: 'blue'
      }, 10);
    }
  }

  // Detecta quando o app é instalado
  window.addEventListener('appinstalled', () => {
    console.log('[PWA] App instalado com sucesso!');
    if (frappe && frappe.show_alert) {
      frappe.show_alert({
        message: __('GRIS foi instalado com sucesso!'),
        indicator: 'green'
      }, 5);
    }
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
    // Adiciona um banner ou botão para instalar o app
    if (frappe && frappe.show_alert) {
      const installButton = `
        <div style="display: flex; align-items: center; justify-content: space-between;">
          <span>${__('Instalar GRIS no seu dispositivo')}</span>
          <button class="btn btn-primary btn-sm" onclick="window.installPWA()" style="margin-left: 10px;">
            ${__('Instalar')}
          </button>
        </div>
      `;
      
      frappe.show_alert({
        message: installButton,
        indicator: 'blue'
      }, 20);
    }
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
