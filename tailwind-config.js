tailwind.config = {
    theme: {
        extend: {
            fontFamily: {
                poppins: ['Poppins', 'sans-serif'],
            },
            colors: {
                'brand-blue': {
                    DEFAULT: '#5060FF',
                    dark: '#3F4CCC', 
                    light: '#8A94FF',
                },
                'brand-gray': {
                    DEFAULT: '#3B3B3B',
                    light: '#F5F5FB',
                    border: '#EBEBEB',
                    text: '#555555' 
                },
                'brand-viz': {
                    bg: '#f0f1ff',
                    border: '#C9CEFF',
                }
            },
            backgroundImage: {
                'btn-gradient': 'linear-gradient(273deg, #5060FF 13.62%, #8A94FF 111.34%)',
                'btn-gradient-hover': 'linear-gradient(0deg, rgba(0,0,0,0.3) 0%, rgba(0,0,0,0.3) 100%), linear-gradient(273deg, #5060FF 13.62%, #8A94FF 111.34%)',
            },
            boxShadow: {
                'primary': '0px 12px 20px rgba(80, 96, 255, 0.12)',
                'button': '0px 10px 40px rgba(80, 96, 255, 0.25)',
            }
        }
    }
}
