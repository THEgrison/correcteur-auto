"""Point d'entrée : python -m correcteur"""

from correcteur.instance import acquire_or_exit
from correcteur.app import main

if __name__ == "__main__":
    acquire_or_exit()
    main()
