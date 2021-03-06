from src.train import Trainer
from dataloader.dataloader import get_loader
import os
from config.config import get_config


def main(config):
    if config.checkpoint_dir is None:
        config.checkpoint_dir = 'checkpoints'

    if not os.path.exists(config.checkpoint_dir):
        os.makedirs(config.checkpoint_dir)

    if not os.path.exists(config.sample_dir):
        os.makedirs(config.sample_dir)

    print(f"{config.style} CycleGAN")

    from_style = config.style.split('2')[0]
    to_style = config.style.split('2')[1]

    data_loader = get_loader(from_style, to_style, config)
    trainer = Trainer(config, data_loader)
    trainer.train()


if __name__ == "__main__":
    config = get_config()
    main(config)
