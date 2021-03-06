import torch
from utils.utils import LambdaLR
import torch.optim
import itertools
import torch.nn as nn
from model import build_model
import torch.optim.lr_scheduler
import os
from torchvision.utils import save_image


class Trainer:
    def __init__(self, config, data_loader):
        self.device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
        self.num_epoch = config.num_epoch
        self.data_loader = data_loader
        self.batch_size = config.batch_size
        self.lambda_cycle = config.lambda_cycle
        self.lambda_identity = config.lambda_identity
        self.checkpoint_dir = config.checkpoint_dir
        self.from_style = config.style.split('2')[0]
        self.to_style = config.style.split('2')[1]
        self.sample_dir = config.sample_dir
        self.epoch = config.epoch
        self.generator_ab, self.generator_ba, self.discriminator_a, self.discriminator_b = build_model(config, self.from_style, self.to_style)
        self.optimizer_G = torch.optim.Adam(itertools.chain(self.generator_ab.parameters(), self.generator_ba.parameters()), lr=config.lr, betas=(config.b1, config.b2))
        self.optimizer_D_A = torch.optim.Adam(self.discriminator_a.parameters(), lr=config.lr, betas=(config.b1, config.b2))
        self.optimizer_D_B = torch.optim.Adam(self.discriminator_b.parameters(), lr=config.lr, betas=(config.b1, config.b2))

        self.lr_scheduler_G = torch.optim.lr_scheduler.StepLR(self.optimizer_G, config.decay_epoch, 0.5)
        self.lr_scheduler_D_A = torch.optim.lr_scheduler.StepLR(self.optimizer_D_A, config.decay_epoch, 0.5)
        self.lr_scheduler_D_B = torch.optim.lr_scheduler.StepLR(self.optimizer_D_B, config.decay_epoch, 0.5)

        self.criterion_gan = nn.BCELoss().to(self.device)
        # self.criterion_gan = nn.MSELoss().to(self.device)
        self.criterion_cycle = nn.L1Loss().to(self.device)
        self.criterion_identity = nn.L1Loss().to(self.device)

    def train(self):
        if not os.path.exists(os.path.join(self.checkpoint_dir, f"{self.from_style}2{self.to_style}")):
            os.makedirs(os.path.join(self.checkpoint_dir, f"{self.from_style}2{self.to_style}"))
        style_dir = os.path.join(self.sample_dir, f"{self.from_style}2{self.to_style}")
        if not os.path.exists(style_dir):
            os.makedirs(style_dir)

        self.generator_ab.train()
        self.generator_ba.train()

        for epoch in range(self.epoch, self.num_epoch):
            if not os.path.exists(os.path.join(style_dir, str(epoch))):
                os.makedirs(os.path.join(style_dir, str(epoch)))
            for step, image in enumerate(self.data_loader):
                total_step = len(self.data_loader)


                real_image_a = image["A"].to(self.device)
                real_image_b = image["B"].to(self.device)

                real_labels = torch.ones((real_image_a.size(0), *self.discriminator_a.output_shape)).to(self.device)
                fake_labels = torch.zeros((real_image_a.size(0), *self.discriminator_a.output_shape)).to(self.device)

                # ---------------
                # train generator
                # ---------------

                # make image
                fake_image_b = self.generator_ab(real_image_a)
                fake_image_a = self.generator_ba(real_image_b)

                # gan loss
                gan_ab_loss = self.criterion_gan(self.discriminator_a(fake_image_a), real_labels)
                gan_ba_loss = self.criterion_gan(self.discriminator_b(fake_image_b), real_labels)
                gan_loss = (gan_ab_loss + gan_ba_loss) / 2

                # cycle loss
                cycle_loss_a = self.criterion_cycle(self.generator_ba(fake_image_b), real_image_a)
                cycle_loss_b = self.criterion_cycle(self.generator_ab(fake_image_a), real_image_b)
                cycle_loss = (cycle_loss_a + cycle_loss_b) / 2

                # identity loss
                identity_a_loss = self.criterion_identity(self.generator_ba(real_image_a), real_image_a)
                identity_b_loss = self.criterion_identity(self.generator_ab(real_image_b), real_image_b)
                identity_loss = (identity_a_loss + identity_b_loss) / 2

                generator_loss = gan_loss + self.lambda_cycle * cycle_loss + self.lambda_identity * identity_loss

                self.optimizer_G.zero_grad()
                generator_loss.backward()
                self.optimizer_G.step()

                # ---------------------
                # train discriminator A
                # ---------------------
                fake_image_a = self.generator_ba(real_image_b)
                real_loss_a = self.criterion_gan(self.discriminator_a(real_image_a), real_labels)
                fake_loss_a = self.criterion_gan(self.discriminator_a(fake_image_a), fake_labels)
                discriminator_a_loss = (real_loss_a + fake_loss_a) / 2

                self.optimizer_D_A.zero_grad()
                discriminator_a_loss.backward()
                self.optimizer_D_A.step()

                # ---------------------
                # train discriminator B
                # ---------------------
                fake_image_b = self.generator_ab(real_image_a)
                real_loss_b = self.criterion_gan(self.discriminator_b(real_image_b), real_labels)
                fake_loss_b = self.criterion_gan(self.discriminator_b(fake_image_b), fake_labels)
                discriminator_b_loss = (real_loss_b + fake_loss_b) / 2

                self.optimizer_D_B.zero_grad()
                discriminator_b_loss.backward()
                self.optimizer_D_B.step()

                discriminator_loss = (discriminator_a_loss + discriminator_b_loss) / 2

                if step % 10 == 0:
                    print(f"[Epoch {epoch}/{self.num_epoch}] [Batch {step}/{total_step}] "
                          f"[D loss: {discriminator_loss.item():.4f}] [G loss: {generator_loss.item():.4f}, "
                          f"adv: {gan_loss.item():.4f}, cycle: {cycle_loss.item():.4f}, identity: {identity_loss.item():.4f}]")
                    if step % 50 == 0:
                        style_image_a = torch.cat([real_image_a, fake_image_b], 2)
                        style_image_b = torch.cat([real_image_b, fake_image_a], 2)
                        save_image(style_image_a, f"{self.sample_dir}/{self.from_style}2{self.to_style}/{epoch}/{step}_{self.from_style}2{self.to_style}.png", normalize=False)
                        save_image(style_image_b, f"{self.sample_dir}/{self.from_style}2{self.to_style}/{epoch}/{step}_{self.to_style}2{self.from_style}.png", normalize=False)

            self.lr_scheduler_D_A.step()
            self.lr_scheduler_D_B.step()
            self.lr_scheduler_G.step()

            torch.save(self.generator_ab.state_dict(), os.path.join(self.checkpoint_dir, f"{self.from_style}2{self.to_style}", f"generator_ab_{epoch}.pth"))
            torch.save(self.generator_ba.state_dict(), os.path.join(self.checkpoint_dir, f"{self.from_style}2{self.to_style}", f"generator_ba_{epoch}.pth"))
            torch.save(self.discriminator_a.state_dict(), os.path.join(self.checkpoint_dir, f"{self.from_style}2{self.to_style}", f"discriminator_a_{epoch}.pth"))
            torch.save(self.discriminator_b.state_dict(), os.path.join(self.checkpoint_dir, f"{self.from_style}2{self.to_style}", f"discriminator_b_{epoch}.pth"))
