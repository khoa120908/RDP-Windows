(() => {
    if (window.__CAPTCHA_HOOK_INSTALLED__) return;
    window.__CAPTCHA_HOOK_INSTALLED__ = true;

    function waitForSliderElement() {
        return new Promise(resolve => {
            const slider = document.querySelector('.slider');
            if (slider) return resolve(slider);

            const observer = new MutationObserver(() => {
                const slider = document.querySelector('.slider');

                if (slider) {
                    observer.disconnect();
                    resolve(slider);
                }
            });

            observer.observe(document.documentElement, {
                childList: true,
                subtree: true
            });
        });
    }

    async function solveCaptcha() {
        const slider = await waitForSliderElement();
        const bounding = slider.getBoundingClientRect();
        const startX = bounding.left + bounding.width / 2;
        const startY = bounding.top + bounding.height / 2;

        const createTouch = x => new Touch({
            identifier: Date.now(),
            target: slider,
            clientX: x,
            clientY: startY
        });

        const dispatchTouch = (type, x) => slider.dispatchEvent(new TouchEvent(type, {
            bubbles: true,
            cancelable: true,
            touches: type === 'touchend' ? [] : [createTouch(x)],
            changedTouches: [createTouch(x)]
        }));

        dispatchTouch('touchstart', startX);

        for (let step = 1; step <= 50; step++) {
            dispatchTouch('touchmove', startX + 350 * step / 50);
            await new Promise(resolve => setTimeout(resolve, 10));
        }

        dispatchTouch('touchend', startX + 350);
    }

    let Callback = window.captchaCallback;
    Object.defineProperty(window, 'captchaCallback', {
        get() {
            return Callback;
        },
        set(onCallback) {
            Callback = onCallback;
            solveCaptcha();
        },
        configurable: true
    });
})();
