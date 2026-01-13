(function() {
    document.addEventListener('DOMContentLoaded', function() {
        const container = document.querySelector('.flow-steps-container');
        if (!container) return;

        const doneSteps = container.querySelectorAll('.flow-step.done');
        
        if (doneSteps.length > 0) {
            const lastDoneStep = doneSteps[doneSteps.length - 1];
            
            // Calculate the position to center the element
            const scrollPos = lastDoneStep.offsetLeft + (lastDoneStep.offsetWidth / 2) - (container.offsetWidth / 2);
            
            // Apply scroll
            container.scrollTo({
                left: scrollPos,
                behavior: 'smooth'
            });
        }
    });
})();
